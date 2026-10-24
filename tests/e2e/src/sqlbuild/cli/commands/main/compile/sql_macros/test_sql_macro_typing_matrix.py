"""E2E matrix of SQL macro calls typed by their returns in every position a call can stand."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile.sql_macros.helpers import (
    BRACKET,
    contract_model,
    orders_model,
    output,
    run_project,
    text_macro,
    with_rules,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb


@dataclass(frozen=True)
class TypingPositionTestCase:
    """One position of a call in a contracted model, and whether a known body type disagrees."""

    description: str
    sql: str
    declared: str = "VARCHAR"
    known_disagrees: bool = True


_FROM: str = 'FROM __ref("stg_orders") AS o'
_MACROS: dict[str, str] = {
    **text_macro("status_bar", "VARCHAR", "bar(LENGTH(@value), 0, 10)"),
    **text_macro("same", "VARCHAR", "@value", argument="ANY"),
    **text_macro("shouted", "VARCHAR", "UPPER(@value)"),
}
_POSITIONS: tuple[TypingPositionTestCase, ...] = (
    TypingPositionTestCase("main_whole_item", f"SELECT {{m}} AS x {_FROM}\n"),
    TypingPositionTestCase(
        "cte_item_read_by_name", f"WITH c AS (SELECT {{m}} AS x {_FROM})\nSELECT x FROM c\n"
    ),
    TypingPositionTestCase(
        "star_from_a_cte", f"WITH c AS (SELECT {{m}} AS x {_FROM})\nSELECT * FROM c\n"
    ),
    TypingPositionTestCase("derived_table", f"SELECT s.x FROM (SELECT {{m}} AS x {_FROM}) AS s\n"),
    TypingPositionTestCase(
        "scalar_subquery", f"SELECT (SELECT {{m}} {_FROM} LIMIT 1) AS x\n", known_disagrees=False
    ),
    TypingPositionTestCase(
        "nested_with",
        f"WITH c AS (WITH d AS (SELECT {{m}} AS x {_FROM}) SELECT x FROM d)\nSELECT x FROM c\n",
    ),
    TypingPositionTestCase(
        "union_right_branch",
        f"SELECT o.status AS x {_FROM}\nUNION ALL\nSELECT {{m}} AS x {_FROM}\n",
        known_disagrees=False,
    ),
    TypingPositionTestCase(
        "union_left_branch",
        f"SELECT {{m}} AS x {_FROM}\nUNION ALL\nSELECT o.status AS x {_FROM}\n",
        known_disagrees=False,
    ),
    TypingPositionTestCase(
        "union_both_branches",
        f"SELECT {{m}} AS x {_FROM}\nUNION ALL\nSELECT {{m}} AS x {_FROM}\n",
    ),
    TypingPositionTestCase(
        "parenthesised_branch",
        f"SELECT CAST(NULL AS VARCHAR) AS x {_FROM}\nUNION ALL\n(SELECT {{m}} AS x {_FROM})\n",
        known_disagrees=False,
    ),
    TypingPositionTestCase(
        "after_a_star_modifier",
        "WITH c AS (SELECT o.order_id, o.status " + _FROM + ")\n"
        "SELECT * EXCLUDE (order_id), {m} AS x FROM c AS o\n",
    ),
    TypingPositionTestCase(
        "arithmetic",
        f"SELECT LENGTH({{m}}) + 1 AS x {_FROM}\n",
        declared="BIGINT",
        known_disagrees=False,
    ),
    TypingPositionTestCase(
        "coalesce", f"SELECT COALESCE({{m}}, {{m}}) AS x {_FROM}\n", known_disagrees=False
    ),
    TypingPositionTestCase(
        "case",
        f"SELECT CASE WHEN o.order_id > 1 THEN {{m}} ELSE NULL END AS x {_FROM}\n",
        known_disagrees=False,
    ),
    TypingPositionTestCase(
        "function_argument",
        f"SELECT LENGTH({{m}}) AS x {_FROM}\n",
        declared="BIGINT",
        known_disagrees=False,
    ),
    TypingPositionTestCase(
        "aggregate_over_the_call", f"SELECT MAX({{m}}) AS x {_FROM}\n", known_disagrees=False
    ),
    TypingPositionTestCase(
        "window",
        f"SELECT MAX({{m}}) OVER (ORDER BY o.order_id) AS x {_FROM}\n",
        known_disagrees=False,
    ),
    TypingPositionTestCase("unaliased_call", f"SELECT {{m}} {_FROM}\n", known_disagrees=False),
)


def _model(position: TypingPositionTestCase, call: str) -> dict[str, str]:
    sql: str = position.sql.replace("{m}", call)
    if position.description == "unaliased_call":
        return orders_model(sql)
    if position.description == "after_a_star_modifier":
        return {
            **orders_model(sql),
            **contract_model(
                "order_x", f"x (type {position.declared})", 'SELECT b.x FROM __ref("orders") AS b\n'
            ),
        }
    return contract_model("orders", f"x (type {position.declared})", sql)


@pytest.mark.parametrize("position", _POSITIONS, ids=lambda case: case.description)
def test_given_an_unknown_body_when_compiling_then_the_call_takes_its_returns_type(
    position: TypingPositionTestCase, tmp_path: Path
) -> None:
    _, result = run_project(
        tmp_path=tmp_path,
        files={**_MACROS, **_model(position, "@sql.status_bar(o.status)")},
        command=("compile", "--no-cache"),
    )

    assert result.returncode == 0, output(result)
    assert "0 errors, 0 warnings" in output(result), output(result)


@pytest.mark.parametrize(
    "position",
    [position for position in _POSITIONS if position.known_disagrees],
    ids=lambda case: case.description,
)
def test_given_a_known_different_body_when_compiling_then_the_inferred_type_stands(
    position: TypingPositionTestCase, tmp_path: Path
) -> None:
    _, result = run_project(
        tmp_path=tmp_path,
        files={**_MACROS, **_model(position, "@sql.same(o.order_id)")},
        command=("compile", "--no-cache"),
    )

    assert "error[K002]: column 'x' inferred as" in output(result), output(result)


@dataclass(frozen=True)
class TypingCaseTestCase:
    """One project and what compiling it prints."""

    description: str
    files: dict[str, str]
    expected_returncode: int
    expected_fragments: tuple[str, ...]


@pytest.mark.parametrize(
    "test_case",
    [
        TypingCaseTestCase(
            description="aggregate_inside_the_body",
            files={
                **text_macro("summed", "BIGINT", "SUM(bar(LENGTH(@value), 0, 10))"),
                **contract_model(
                    "orders",
                    "status (type VARCHAR), x (type BIGINT)",
                    f"SELECT o.status, @sql.summed(o.status) AS x {_FROM}\nGROUP BY o.status\n",
                ),
            },
            expected_returncode=0,
            expected_fragments=("0 errors, 0 warnings",),
        ),
        TypingCaseTestCase(
            description="aggregate_inside_the_body_still_needs_group_by",
            files={
                **text_macro("summed", "BIGINT", "SUM(bar(LENGTH(@value), 0, 10))"),
                **orders_model(f"SELECT o.status, @sql.summed(o.status) AS x {_FROM}\n"),
            },
            expected_returncode=1,
            expected_fragments=("error[B230]",),
        ),
        TypingCaseTestCase(
            description="a_nested_call_types_the_macro_calling_it",
            files={
                **_MACROS,
                **text_macro("outer_bar", None, "@sql.status_bar(@value)"),
                **contract_model(
                    "orders", "x (type VARCHAR)", f"SELECT @sql.outer_bar(o.status) AS x {_FROM}\n"
                ),
            },
            expected_returncode=0,
            expected_fragments=("0 errors, 0 warnings",),
        ),
        TypingCaseTestCase(
            description="an_any_argument_of_unknown_type_takes_returns",
            files={
                **_MACROS,
                **contract_model(
                    "orders",
                    "x (type VARCHAR)",
                    f"SELECT @sql.same(bar(o.order_id, 0, 10)) AS x {_FROM}\n",
                ),
            },
            expected_returncode=0,
            expected_fragments=("0 errors, 0 warnings",),
        ),
        TypingCaseTestCase(
            description="a_known_identical_body",
            files={
                **_MACROS,
                **contract_model(
                    "orders", "x (type VARCHAR)", f"SELECT @sql.shouted(o.status) AS x {_FROM}\n"
                ),
            },
            expected_returncode=0,
            expected_fragments=("0 errors, 0 warnings",),
        ),
        TypingCaseTestCase(
            description="a_call_inside_a_python_macro_argument_is_inferred_only",
            files={
                **_MACROS,
                **BRACKET,
                **contract_model(
                    "orders",
                    "x (type VARCHAR)",
                    f"SELECT @py.bracket(@sql.status_bar(o.status)) AS x {_FROM}\n",
                ),
            },
            expected_returncode=0,
            expected_fragments=("0 errors, 0 warnings",),
        ),
        TypingCaseTestCase(
            description="an_outer_cast_wins_and_satisfies_the_cast_rule",
            files={
                **with_rules("SQBRCONTRACT105"),
                **_MACROS,
                **contract_model(
                    "orders",
                    "x (type BIGINT)",
                    f"SELECT CAST(@sql.status_bar(o.status) AS BIGINT) AS x {_FROM}\n",
                ),
            },
            expected_returncode=0,
            expected_fragments=("0 errors, 0 warnings",),
        ),
        TypingCaseTestCase(
            description="a_call_inside_arithmetic_needs_a_cast_for_the_cast_rule",
            files={
                **with_rules("SQBRCONTRACT105"),
                **_MACROS,
                **contract_model(
                    "orders",
                    "x (type BIGINT)",
                    f"SELECT LENGTH(@sql.status_bar(o.status)) + 1 AS x {_FROM}\n",
                ),
            },
            expected_returncode=1,
            expected_fragments=(
                'error[SQBRCONTRACT105]: output "x" is calculated without an outer explicit cast',
                "Wrap the complete expression in CAST(... AS BIGINT)",
            ),
        ),
        TypingCaseTestCase(
            description="a_binding_error_after_a_call_is_located_where_it_was_written",
            files={
                **_MACROS,
                **orders_model(f"SELECT @sql.status_bar(o.status) AS x, o.missing {_FROM}\n"),
            },
            expected_returncode=1,
            expected_fragments=("--> models/marts/orders.sql:3:42",),
        ),
        TypingCaseTestCase(
            description="the_reserved_analysis_function_is_rejected_in_a_model",
            files={**orders_model(f"SELECT __polyglot_typed(o.status, 'VARCHAR') AS x {_FROM}\n")},
            expected_returncode=1,
            expected_fragments=("uses __polyglot_typed, a name reserved for SQL analysis",),
        ),
        TypingCaseTestCase(
            description="a_downstream_model_sees_the_returns_type",
            files={
                **_MACROS,
                **contract_model(
                    "orders", "x (type VARCHAR)", f"SELECT @sql.status_bar(o.status) AS x {_FROM}\n"
                ),
                **contract_model(
                    "order_labels", "x (type BIGINT)", 'SELECT b.x FROM __ref("orders") AS b\n'
                ),
            },
            expected_returncode=1,
            expected_fragments=("error[K002]: column 'x' inferred as",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_typed_call_case_when_compiling_then_it_reports_as_expected(
    test_case: TypingCaseTestCase, tmp_path: Path
) -> None:
    _, result = run_project(
        tmp_path=tmp_path, files=test_case.files, command=("compile", "--no-cache")
    )

    assert result.returncode == test_case.expected_returncode, output(result)
    for fragment in test_case.expected_fragments:
        assert fragment in output(result), output(result)


@pytest.mark.xfail(
    reason="a * REPLACE item takes its source column's type; a known polyglot gap", strict=True
)
def test_given_a_call_in_a_star_replace_when_compiling_then_it_takes_its_returns_type(
    tmp_path: Path,
) -> None:
    _, result = run_project(
        tmp_path=tmp_path,
        files={
            **_MACROS,
            **contract_model(
                "orders",
                "order_id (type VARCHAR)",
                "WITH c AS (SELECT o.order_id " + _FROM + ")\n"
                "SELECT * REPLACE (@sql.status_bar(CAST(order_id AS VARCHAR)) AS order_id) "
                "FROM c\n",
            ),
        },
        command=("compile", "--no-cache"),
    )

    assert "0 errors, 0 warnings" in output(result), output(result)


def test_given_typed_calls_when_compiling_then_the_compiled_sql_has_no_marker(
    tmp_path: Path,
) -> None:
    project_dir, result = run_project(
        tmp_path=tmp_path,
        files={
            **_MACROS,
            **contract_model(
                "orders", "x (type VARCHAR)", f"SELECT @sql.status_bar(o.status) AS x {_FROM}\n"
            ),
        },
        command=("compile", "--no-cache"),
    )
    compiled: list[Path] = [
        path for path in (project_dir / "target").rglob("orders.sql") if "compiled" in str(path)
    ]

    assert result.returncode == 0, output(result)
    assert compiled, output(result)
    text: str = compiled[0].read_text(encoding="utf-8")
    assert "bar(LENGTH(o.status), 0, 10) AS x" in text, text
    assert "__polyglot" not in text, text


def test_given_a_call_when_reading_lineage_then_it_matches_the_inline_sql(tmp_path: Path) -> None:
    macro_dir, _ = run_project(
        tmp_path=tmp_path / "macro",
        files={
            **text_macro("ident", "BIGINT", "@value", argument="BIGINT"),
            **orders_model(f"SELECT @sql.ident(o.order_id) AS x {_FROM}\n"),
        },
        command=("compile", "--no-cache"),
    )
    inline_dir, _ = run_project(
        tmp_path=tmp_path / "inline",
        files=orders_model(f"SELECT o.order_id AS x {_FROM}\n"),
        command=("compile", "--no-cache"),
    )
    lineage = ("--no-color", "lineage", "orders.x", "--format", "list")
    through_macro: subprocess.CompletedProcess[str] = run_sqb(
        command=lineage, project_dir=macro_dir
    )
    inline: subprocess.CompletedProcess[str] = run_sqb(command=lineage, project_dir=inline_dir)

    assert through_macro.returncode == 0, output(through_macro)
    assert "stg_orders.order_id -> orders.x" in through_macro.stdout, output(through_macro)
    assert _edges(through_macro.stdout) == _edges(inline.stdout)


def _edges(printed: str) -> list[str]:
    """The lineage edges a list-format lineage command printed."""

    return [line.strip() for line in printed.splitlines() if "->" in line]
