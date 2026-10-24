"""E2E coverage for optional SQL macro returns types and the check of returns against the body."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile.sql_macros._test_types import (
    SqlMacroCompileTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.sql_macros.helpers import (
    contract_model,
    output,
    run_project,
    text_macro,
    with_rules,
)

_UNTYPED_UPSTREAM: dict[str, str] = {
    "models/marts/up.sql": (
        'MODEL (description "Up");\n\nSELECT NULL AS s FROM __ref("stg_orders") AS o\n'
    ),
}
_UNTYPED_CALL: str = 'SELECT @sql.m(u.s) AS v FROM __ref("up") AS u\n'


@pytest.mark.parametrize(
    "test_case",
    [
        SqlMacroCompileTestCase(
            description="a_macro_without_returns_is_typed_from_its_body",
            files={
                **text_macro("m", None, "UPPER(@value)"),
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
                **text_macro("m", None, "LENGTH(@value)"),
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
                **text_macro("m", None, "@value", argument="ANY"),
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
                **text_macro("m", None, "UPPER(@value)"),
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
