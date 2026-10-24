"""E2E coverage for optional SQL macro returns types and the check of returns against the body."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile.sql_macros._test_types import (
    SqlMacroCompileTestCase,
    SqlMacroWarmCompileTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.sql_macros.helpers import (
    contract_model,
    orders_model,
    output,
    run_project,
    text_macro,
    untyped_text_macro,
    with_rules,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb

_UNTYPED_UPSTREAM: dict[str, str] = {
    "models/marts/up.sql": (
        'MODEL (description "Up");\n\nSELECT NULL AS s FROM __ref("stg_orders") AS o\n'
    ),
}
_UNTYPED_CALL: str = 'SELECT @sql.m(u.s) AS v FROM __ref("up") AS u\n'
_FIRST_OF: dict[str, str] = {
    "macros/sql/first_of.sql": (
        'MACRO (\n  description "The first of two values",\n'
        "  arguments (value ANY, other ANY),\n  returns TYPE OF value,\n);\n\n"
        "list_extract([@value, @other], 1)\n"
    )
}
_FIRST_OF_UNTYPED: dict[str, str] = {
    "macros/sql/first_of.sql": _FIRST_OF["macros/sql/first_of.sql"].replace(
        "  returns TYPE OF value,\n", ""
    )
}
_DAY: str = "CAST(o.{column} AS DATE)"
_DAYS: str = f"{_DAY.format(column='created_at')}, {_DAY.format(column='updated_at')}"
_TYPE_OF_POSITIONS: str = (
    "WITH c AS (\n"
    f"  SELECT o.order_id, @sql.first_of({_DAYS}) AS in_cte\n"
    '  FROM __ref("stg_orders") AS o\n'
    ")\n"
    "SELECT\n"
    "  @sql.first_of(o.status, o.country_code) AS text_value,\n"
    f"  @sql.first_of({_DAYS}) AS day_value,\n"
    "  c.in_cte,\n"
    f"  COALESCE(@sql.first_of({_DAYS}), {_DAY.format(column='created_at')}) AS nested\n"
    'FROM __ref("stg_orders") AS o\nJOIN c ON c.order_id = o.order_id\n'
)
_TYPE_OF_COLUMNS: str = (
    "text_value (type VARCHAR), day_value (type DATE), in_cte (type DATE), nested (type DATE)"
)
_TYPE_OF_UNION: str = (
    'SELECT CAST(NULL AS DATE) AS day_value FROM __ref("stg_orders") AS o\n'
    "UNION ALL\n"
    f'SELECT @sql.first_of({_DAYS}) AS day_value FROM __ref("stg_orders") AS o\n'
)
_VARIANT_PATHS: str = (
    "WITH raw AS (SELECT PARSE_JSON('{{\"a\": 1}}') AS payload)\n"
    "SELECT @sql.payload_value({path}) AS v FROM raw\n"
)
_SNOWFLAKE_PROJECT: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "shop"\nadapter = "snowflake"\ndefault_target = "dev"\n\n'
        '[targets.dev]\ndatabase = "warehouse"\nschema = "analytics"\n\n'
        "[scopes]\nenforce_placement = false\n"
    )
}
_ROUNDED: dict[str, str] = {
    "macros/sql/rounded.sql": (
        'MACRO (\n  description "Rounded to places",\n'
        "  arguments (value ANY NUMERIC, places INT CONST DEFAULT 2),\n"
        "  returns TYPE OF value,\n);\n\nROUND(@value, @places)\n"
    ),
    "macros/sql/shouted.sql": (
        'MACRO (\n  description "Shouted",\n  arguments (value ANY TEXT),\n'
        "  returns TYPE OF value,\n);\n\nUPPER(@value)\n"
    ),
    "macros/sql/month_of.sql": (
        'MACRO (\n  description "Month start",\n  arguments (value ANY TEMPORAL),\n'
        "  returns TYPE OF value,\n);\n\nDATE_TRUNC('month', @value)\n"
    ),
}


@pytest.mark.parametrize(
    "test_case",
    [
        SqlMacroCompileTestCase(
            description="a_macro_without_returns_is_typed_from_its_body",
            files={
                **untyped_text_macro("m", "UPPER(@value)"),
                **contract_model(
                    "orders",
                    "v (type VARCHAR)",
                    'SELECT @sql.m(o.status) AS v FROM __ref("stg_orders") AS o\n',
                ),
            },
            expected_returncode=0,
            expected_fragments=("0 errors, 0 warnings",),
        ),
        SqlMacroCompileTestCase(
            description="a_macro_without_returns_keeps_a_known_body_type_that_disagrees",
            files={
                **untyped_text_macro("m", "LENGTH(@value)"),
                **contract_model(
                    "orders",
                    "v (type VARCHAR)",
                    'SELECT @sql.m(o.status) AS v FROM __ref("stg_orders") AS o\n',
                ),
            },
            expected_returncode=1,
            expected_fragments=("error[K002]: column 'v' inferred as BIGINT",),
        ),
        SqlMacroCompileTestCase(
            description="a_macro_with_matching_returns_compiles",
            files={
                **text_macro("m", "VARCHAR", "UPPER(@value)"),
                **contract_model(
                    "orders",
                    "v (type VARCHAR)",
                    'SELECT @sql.m(o.status) AS v FROM __ref("stg_orders") AS o\n',
                ),
            },
            expected_returncode=0,
            expected_fragments=("0 errors, 0 warnings",),
        ),
        SqlMacroCompileTestCase(
            description="a_wrong_returns_is_reported_at_the_macro_file",
            files={
                **text_macro("m", "BIGINT", "UPPER(@value)"),
                **contract_model(
                    "orders",
                    "v (type BIGINT)",
                    'SELECT @sql.m(o.status) AS v FROM __ref("stg_orders") AS o\n',
                ),
            },
            expected_returncode=1,
            expected_fragments=(
                "error[P024]: macro m() declares returns BIGINT, but its body is VARCHAR\n"
                "  model: orders\n"
                "  --> macros/sql/m.sql:7:1",
            ),
        ),
        SqlMacroCompileTestCase(
            description="an_any_argument_leaves_the_body_unknown_so_returns_is_trusted",
            files={
                **with_rules("SQBRCONTRACT105"),
                **text_macro("m", "BIGINT", "@value", argument="ANY"),
                **_UNTYPED_UPSTREAM,
                **contract_model("orders", "v (type BIGINT)", _UNTYPED_CALL),
            },
            expected_returncode=0,
            expected_fragments=("0 errors, 0 warnings",),
        ),
        SqlMacroCompileTestCase(
            description="an_untyped_call_without_returns_suggests_returns_on_k003",
            files={
                **untyped_text_macro("m", "@value", argument="ANY"),
                **_UNTYPED_UPSTREAM,
                **contract_model("orders", "v (type BIGINT)", _UNTYPED_CALL),
            },
            expected_returncode=0,
            expected_fragments=(
                "warning[K003]: column 'v' type could not be proven against declared BIGINT",
                "declare returns BIGINT in SQL macro m(), or add an explicit CAST",
            ),
        ),
        SqlMacroCompileTestCase(
            description="an_untyped_call_without_returns_suggests_returns_on_the_cast_rule",
            files={
                **with_rules("SQBRCONTRACT105"),
                **untyped_text_macro("m", "UPPER(@value)"),
                **contract_model(
                    "orders",
                    "v (type VARCHAR)",
                    'SELECT @sql.m(o.status) AS v FROM __ref("stg_orders") AS o\n',
                ),
            },
            expected_returncode=1,
            expected_fragments=(
                'error[SQBRCONTRACT105]: output "v" is calculated without an outer explicit cast',
                "Declare returns VARCHAR in SQL macro m(), or wrap the call in CAST(... AS VARCHAR).",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_optional_returns_when_compiling_then_calls_are_typed_and_checked(
    test_case: SqlMacroCompileTestCase, tmp_path: Path
) -> None:
    _, result = run_project(
        tmp_path=tmp_path, files=test_case.files, command=("compile", "--no-cache")
    )

    assert result.returncode == test_case.expected_returncode, output(result)
    for fragment in test_case.expected_fragments:
        assert fragment in output(result), output(result)
    for fragment in test_case.unexpected_fragments:
        assert fragment not in output(result), output(result)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlMacroCompileTestCase(
            description="returns_type_of_gives_each_call_its_argument_type",
            files={
                **_FIRST_OF,
                **contract_model("orders", _TYPE_OF_COLUMNS, _TYPE_OF_POSITIONS),
            },
            expected_returncode=0,
            expected_fragments=("0 errors, 0 warnings",),
        ),
        SqlMacroCompileTestCase(
            description="returns_type_of_types_a_later_union_branch",
            files={
                **with_rules("SQBRCONTRACT105"),
                **_FIRST_OF,
                **contract_model("orders", "day_value (type DATE)", _TYPE_OF_UNION),
            },
            expected_returncode=0,
            expected_fragments=("0 errors, 0 warnings",),
        ),
        SqlMacroCompileTestCase(
            description="without_returns_the_same_calls_stay_untyped",
            files={
                **_FIRST_OF_UNTYPED,
                **contract_model("orders", _TYPE_OF_COLUMNS, _TYPE_OF_POSITIONS),
            },
            expected_returncode=0,
            expected_fragments=(
                "warning[K003]: column 'text_value' type could not be proven against declared "
                "VARCHAR",
                "warning[K003]: column 'day_value' type could not be proven against declared DATE",
                "warning[K003]: column 'in_cte' type could not be proven against declared DATE",
                "declare returns DATE in SQL macro first_of()",
            ),
        ),
        SqlMacroCompileTestCase(
            description="returns_type_of_a_cast_variant_path_is_variant",
            files={
                **_SNOWFLAKE_PROJECT,
                **text_macro("payload_value", "TYPE OF value", "@value", argument="ANY"),
                **contract_model(
                    "orders",
                    "v (type VARIANT)",
                    _VARIANT_PATHS.format(path="raw.payload:a::VARIANT"),
                ),
            },
            expected_returncode=0,
            expected_fragments=("0 errors, 0 warnings",),
        ),
        SqlMacroCompileTestCase(
            description="returns_type_of_a_bare_variant_path_stays_unknown_like_the_path",
            files={
                **_SNOWFLAKE_PROJECT,
                **text_macro("payload_value", "TYPE OF value", "@value", argument="ANY"),
                **contract_model(
                    "orders", "v (type VARIANT)", _VARIANT_PATHS.format(path="raw.payload:a")
                ),
            },
            expected_returncode=0,
            expected_fragments=(
                "warning[K003]: column 'v' type could not be proven against declared VARIANT",
            ),
        ),
        SqlMacroCompileTestCase(
            description="returns_type_of_an_unknown_argument_stays_unknown",
            files={
                **_FIRST_OF,
                **contract_model(
                    "orders",
                    "v (type VARCHAR)",
                    "SELECT @sql.first_of(bar(o.amount_cents, 0, 10), o.status) AS v\n"
                    'FROM __ref("stg_orders") AS o\n',
                ),
            },
            expected_returncode=0,
            expected_fragments=(
                "warning[K003]: column 'v' type could not be proven against declared VARCHAR",
            ),
        ),
        SqlMacroCompileTestCase(
            description="returns_type_of_keeps_a_known_body_type_that_differs",
            files={
                **text_macro("m", "TYPE OF value", "LENGTH(@value)", argument="ANY"),
                **contract_model(
                    "orders",
                    "v (type VARCHAR)",
                    'SELECT @sql.m(o.status) AS v FROM __ref("stg_orders") AS o\n',
                ),
            },
            expected_returncode=1,
            expected_fragments=("error[K002]: column 'v' inferred as BIGINT",),
        ),
        SqlMacroCompileTestCase(
            description="returns_type_of_an_unknown_argument_name_is_reported_at_the_macro_file",
            files={
                **text_macro("m", "TYPE OF missing", "@value", argument="ANY"),
                **contract_model(
                    "orders",
                    "v (type VARCHAR)",
                    'SELECT @sql.m(o.status) AS v FROM __ref("stg_orders") AS o\n',
                ),
            },
            expected_returncode=1,
            expected_fragments=(
                "error[P015]: returns TYPE OF missing names no argument of macro m()",
                "macros/sql/m.sql:4:",
            ),
        ),
        SqlMacroCompileTestCase(
            description="returns_type_of_a_list_argument_is_reported_at_the_macro_file",
            files={
                "macros/sql/m.sql": (
                    'MACRO (\n  description "Listed",\n  arguments (codes LIST VARCHAR),\n'
                    "  returns TYPE OF codes,\n);\n\n'GB' IN @codes\n"
                ),
                **contract_model(
                    "orders",
                    "v (type BOOLEAN)",
                    "SELECT @sql.m(['GB']) AS v FROM __ref(\"stg_orders\") AS o\n",
                ),
            },
            expected_returncode=1,
            expected_fragments=(
                "error[P015]: returns TYPE OF codes names a LIST VARCHAR argument of macro m()",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_returns_type_of_when_compiling_then_each_call_has_its_argument_type(
    test_case: SqlMacroCompileTestCase, tmp_path: Path
) -> None:
    _, result = run_project(
        tmp_path=tmp_path, files=test_case.files, command=("compile", "--no-cache")
    )

    assert result.returncode == test_case.expected_returncode, output(result)
    for fragment in test_case.expected_fragments:
        assert fragment in output(result), output(result)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlMacroCompileTestCase(
            description="a_call_of_each_family_in_several_positions",
            files={
                **_ROUNDED,
                **contract_model(
                    "orders",
                    "amount (type BIGINT), loud (type VARCHAR), month (type TIMESTAMP), "
                    "in_cte (type DOUBLE)",
                    "WITH c AS (\n"
                    "  SELECT o.order_id, @sql.rounded(CAST(o.amount_cents AS DOUBLE)) AS in_cte\n"
                    '  FROM __ref("stg_orders") AS o\n)\n'
                    "SELECT @sql.rounded(o.amount_cents, 0) AS amount,\n"
                    "  @sql.shouted(o.status) AS loud,\n"
                    "  @sql.month_of(o.created_at) AS month,\n"
                    "  c.in_cte\n"
                    'FROM __ref("stg_orders") AS o JOIN c ON c.order_id = o.order_id\n',
                ),
            },
            expected_returncode=0,
            expected_fragments=("0 errors, 0 warnings",),
        ),
        SqlMacroCompileTestCase(
            description="an_unknown_argument_type_is_accepted",
            files={
                **_ROUNDED,
                **orders_model(
                    "SELECT @sql.rounded(bar(o.amount_cents, 0, 10)) AS v "
                    'FROM __ref("stg_orders") AS o\n'
                ),
            },
            expected_returncode=0,
            expected_fragments=("0 errors",),
        ),
        SqlMacroCompileTestCase(
            description="a_wrong_family_argument_is_reported_at_the_call",
            files={
                **_ROUNDED,
                **orders_model(
                    'SELECT @sql.rounded(o.status) AS v FROM __ref("stg_orders") AS o\n'
                ),
            },
            expected_returncode=1,
            expected_fragments=(
                "argument value of macro rounded() expects a number; o.status is VARCHAR",
                "models/marts/orders.sql:3:",
            ),
        ),
        SqlMacroCompileTestCase(
            description="a_wrong_family_literal_is_reported_at_the_call",
            files={
                **_ROUNDED,
                **orders_model("SELECT @sql.shouted(12) AS v\n"),
            },
            expected_returncode=1,
            expected_fragments=(
                "error[P017]: argument value of macro shouted() expects text; 12 is an integer",
            ),
        ),
        SqlMacroCompileTestCase(
            description="a_body_wrong_for_its_family_is_reported_at_the_macro_file",
            files={
                "macros/sql/m.sql": (
                    'MACRO (\n  description "Shouted number",\n  arguments (value ANY NUMERIC),\n'
                    ");\n\nUPPER(@value)\n"
                ),
                **orders_model(
                    'SELECT @sql.m(o.amount_cents) AS v FROM __ref("stg_orders") AS o\n'
                ),
            },
            expected_returncode=1,
            expected_fragments=(
                "error[P025]: body of macro m() does not accept every value of value ANY NUMERIC",
                "--> macros/sql/m.sql:6:1",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_any_type_families_when_compiling_then_calls_and_bodies_are_checked(
    test_case: SqlMacroCompileTestCase, tmp_path: Path
) -> None:
    _, result = run_project(
        tmp_path=tmp_path, files=test_case.files, command=("compile", "--no-cache")
    )

    assert result.returncode == test_case.expected_returncode, output(result)
    for fragment in test_case.expected_fragments:
        assert fragment in output(result), output(result)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlMacroWarmCompileTestCase(
            description="removing_returns_type_of",
            files={
                **_FIRST_OF,
                **contract_model("orders", "day_value (type DATE)", _TYPE_OF_UNION),
            },
            edited_path="macros/sql/first_of.sql",
            replaced_text=("  returns TYPE OF value,\n", ""),
            expected_cold_fragment="0 errors, 0 warnings",
            expected_warm_fragment="warning[K003]: column 'day_value'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_changed_returns_form_when_compiling_warm_then_the_cache_is_not_reused(
    test_case: SqlMacroWarmCompileTestCase, tmp_path: Path
) -> None:
    project_dir, cold = run_project(tmp_path=tmp_path, files=test_case.files, command=("compile",))
    macro: Path = project_dir / test_case.edited_path
    old, new = test_case.replaced_text
    macro.write_text(macro.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    warm: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile"), project_dir=project_dir
    )

    assert test_case.expected_cold_fragment in output(cold), output(cold)
    assert test_case.expected_warm_fragment in output(warm), output(warm)
