"""The rules request reads model facts the compile-input stage retained natively."""

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.cli.entry.main.entry import main
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.scopes.exceptions import InvalidQualifiedIdentityError
from tests.integration.src.sqlbuild.compiler.compiled_project._test_types import (
    ImmediateSyntaxErrorTestCase,
    ModelLoopErrorTestCase,
    ModelLoopParityTestCase,
    ModelPathScopeErrorTestCase,
    RetainedRulesRowsTestCase,
    UnretainedRulesRowsTestCase,
    ZeroMaterializationTestCase,
)
from tests.integration.src.sqlbuild.compiler.compiled_project.helpers import (
    HEADER_CONTRACT_FILES,
    LEGACY_PROJECT_TYPES,
    MACRO_FILES,
    MODEL_SCHEMA_FILES,
    OPT_OUT_FILES,
    PARITY_FILES,
    PYTHON_HOOK_FILES,
    PYTHON_HOOK_PARITY_FILES,
    TYPE_PROOF_FILES,
    WAFFLE_SHOP_NATIVE_MODELS,
    build_inputs_with_native_loop,
    copy_project,
    count_legacy_constructions,
    expected_summary,
    forbid_hand_built_projects,
    inputs_summary,
    skip_model_retention,
)
from tests.integration.src.sqlbuild.compiler.graph.helpers import ORDERS_PROJECT_FILES, write_files


@pytest.mark.parametrize(
    "test_case",
    [
        RetainedRulesRowsTestCase(
            description="compile proves the passthrough from retained facts",
            expected_codes=("K002", "SQBRCONTRACT105"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_compiled_project_when_evaluating_rules_then_retained_model_facts_are_read(
    test_case: RetainedRulesRowsTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_files(project_dir=tmp_path, files=TYPE_PROOF_FILES)
    forbid_hand_built_projects(monkeypatch=monkeypatch)

    _ = main(["--project-dir", str(tmp_path), "compile", "--json", "--no-cache"])
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)

    assert tuple(item["code"] for item in payload["diagnostics"]) == test_case.expected_codes


@pytest.mark.parametrize(
    "test_case",
    [
        UnretainedRulesRowsTestCase(
            description="models the compile-input stage did not retain",
            expected_error="compiled model 'orders' has no retained compile facts",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unretained_model_facts_when_evaluating_rules_then_compile_reports_it(
    test_case: UnretainedRulesRowsTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_files(project_dir=tmp_path, files=TYPE_PROOF_FILES)
    skip_model_retention(monkeypatch=monkeypatch)

    exit_code: int = main(["--project-dir", str(tmp_path), "compile", "--no-cache"])
    output: str = "".join(capsys.readouterr())

    assert exit_code == 1
    assert test_case.expected_error in output


@pytest.mark.parametrize(
    "test_case",
    [
        ModelLoopParityTestCase(
            description="plain, interpolated, seeded, incremental, column-contract, enum, constant, macro and hooked models",
            fixtures=(),
            files=PARITY_FILES,
            expected_native_models=9,
            expected_summary="parity",
        ),
        ModelLoopParityTestCase(
            description="dynamic columns, audit factories and enforced enum columns",
            fixtures=(),
            files=HEADER_CONTRACT_FILES,
            expected_native_models=3,
            expected_summary="header_contract",
        ),
        ModelLoopParityTestCase(
            description="accepted and rejected analysis opt-outs and invalid reference calls",
            fixtures=(),
            files=OPT_OUT_FILES,
            expected_native_models=4,
            expected_summary="opt_out",
        ),
        ModelLoopParityTestCase(
            description="named model schemas, augmented and out of scope",
            fixtures=(),
            files=MODEL_SCHEMA_FILES,
            expected_native_models=2,
            expected_summary="model_schema",
        ),
        ModelLoopParityTestCase(
            description="python hooks, checked and scoped",
            fixtures=(),
            files=PYTHON_HOOK_PARITY_FILES,
            expected_native_models=3,
            expected_summary="python_hooks",
        ),
        ModelLoopParityTestCase(
            description="neutral fixture with macros, enums and declared columns",
            fixtures=("tests/e2e/fixtures/waffle_shop",),
            files={},
            expected_native_models=WAFFLE_SHOP_NATIVE_MODELS,
            expected_summary="waffle_shop",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_when_running_native_model_loop_then_inputs_match_recorded_attachment(
    test_case: ModelLoopParityTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = copy_project(
        fixtures=test_case.fixtures, files=test_case.files, project_dir=tmp_path / "project"
    )

    native, native_counts = build_inputs_with_native_loop(
        project_dir=project_dir, monkeypatch=monkeypatch
    )

    assert native_counts == [test_case.expected_native_models]
    assert inputs_summary(inputs=native, project_dir=project_dir) == expected_summary(
        test_case.expected_summary
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ModelLoopErrorTestCase(
            description="blank header description",
            model_sql="MODEL (description ' ');\nSELECT 1 AS order_id\n",
            expected_message="models/orders.sql model 'description' must be a non-empty string",
            expected_code="P001",
        ),
        ModelLoopErrorTestCase(
            description="conflicting analysis overrides",
            model_sql="MODEL (sql_analysis true, sql_validation false);\nSELECT 1 AS order_id\n",
            expected_message="MODEL sql_analysis conflicts with legacy sql_validation",
            expected_code="P003",
        ),
        ModelLoopErrorTestCase(
            description="column rename on a rebuilt table",
            model_sql=(
                "MODEL (materialized table, columns (revenue (migrate_from amount)));\n"
                "SELECT 1 AS revenue\n"
            ),
            expected_message=(
                "model 'orders': column 'revenue' declares migrate_from, which is only valid for "
                "incremental and snapshot models, or for table and view models that declare "
                "migrate_from themselves (the old name's compatibility view then presents the "
                "column under its old name); 'table' models are rebuilt with their new columns"
            ),
            expected_code="P001",
        ),
        ModelLoopErrorTestCase(
            description="invalid dynamic column pattern",
            model_sql=(
                "MODEL (dynamic_columns (amounts (pivot_column category, value_column amount,"
                ' aggregate max, type INTEGER, name_pattern "(")));\n'
                "SELECT 1 AS order_id\n"
            ),
            expected_message=(
                "model 'orders' dynamic column family 'amounts' has invalid name_pattern: "
                "missing ), unterminated subpattern at position 0"
            ),
            expected_code="P001",
        ),
        ModelLoopErrorTestCase(
            description="unknown audit factory",
            model_sql="MODEL (audit_factories [order_checks]);\nSELECT 1 AS order_id\n",
            expected_message=(
                "model 'orders' in models/orders.sql references unknown audit factory "
                "'order_checks'. Available audit factories: none discovered"
            ),
            expected_code="P001",
        ),
        ModelLoopErrorTestCase(
            description="unknown model schema",
            model_sql="MODEL (model_schema order_shape);\nSELECT 1 AS order_id\n",
            expected_message=(
                "model 'orders' references unknown model_schema 'order_shape'; "
                "available schemas: none"
            ),
            expected_code="P001",
        ),
        ModelLoopErrorTestCase(
            description="dbt reference without a dbt manifest",
            model_sql='MODEL ();\nSELECT * FROM __dbt_ref("raw_orders")\n',
            expected_message=(
                'Model file models/orders.sql uses __dbt_ref("raw_orders") but no dbt manifest '
                "was found"
            ),
            expected_code="C214",
        ),
        ModelLoopErrorTestCase(
            description="unclosed reference call located in the model file",
            model_sql='MODEL ();\nSELECT *\nFROM __ref("stg_orders"\n',
            expected_message="models/orders.sql:3:6: SQL reference contains an unclosed parenthesis",
            expected_code="P001",
        ),
        ModelLoopErrorTestCase(
            description="unknown project variable",
            model_sql="MODEL ();\nSELECT '@@missing_var' AS label\n",
            expected_message=(
                "unknown project variable '@@missing_var' in '{model_path}'. Available vars: none"
            ),
            expected_code="P001",
        ),
        ModelLoopErrorTestCase(
            description="python hook that is not discovered",
            model_sql='MODEL (post_hooks [python("flexible"), python("missing")]);\nSELECT 1 AS id\n',
            expected_message=(
                "model 'orders' post_hooks[1] python(\"missing\") references an unknown hook. "
                "Discovered hooks: flexible, notify, positional"
            ),
            expected_code="P001",
            files=PYTHON_HOOK_FILES,
        ),
        ModelLoopErrorTestCase(
            description="python hook argument shadowing a context parameter",
            model_sql=(
                'MODEL (pre_hooks [python("notify", hook_context: "x", ctx: "y")]);\n'
                "SELECT 1 AS id\n"
            ),
            expected_message=(
                "model 'orders' pre_hooks[0] python(\"notify\") argument 'ctx' conflicts with "
                "reserved context parameter 'ctx'. Rename the hook argument; context parameters "
                "are injected by SQLBuild."
            ),
            expected_code="P001",
            files=PYTHON_HOOK_FILES,
        ),
        ModelLoopErrorTestCase(
            description="python hook arguments the function does not accept",
            model_sql=(
                'MODEL (pre_hooks [python("notify", zone: "x", channel: "c", area: "y")]);\n'
                "SELECT 1 AS id\n"
            ),
            expected_message=(
                "model 'orders' pre_hooks[0] python(\"notify\") has unknown argument(s): area, "
                "zone. Accepted configured arguments: channel, level"
            ),
            expected_code="P001",
            files=PYTHON_HOOK_FILES,
        ),
        ModelLoopErrorTestCase(
            description="python hook with a required positional-only parameter",
            model_sql='MODEL (post_hooks [python("positional")]);\nSELECT 1 AS id\n',
            expected_message=(
                "model 'orders' post_hooks[0] python(\"positional\") cannot be configured "
                "because the hook function has required positional-only parameter(s): "
                "warehouse. Use keyword-capable parameters for values supplied from MODEL hooks."
            ),
            expected_code="P001",
            files=PYTHON_HOOK_FILES,
        ),
        ModelLoopErrorTestCase(
            description="python hook missing a required argument after valid hooks",
            model_sql=(
                'MODEL (post_hooks [python("flexible", any: 1)], pre_hooks [python("notify")]);\n'
                "SELECT 1 AS id\n"
            ),
            expected_message=(
                "model 'orders' pre_hooks[0] python(\"notify\") is missing required "
                "argument(s): channel"
            ),
            expected_code="P001",
            files=PYTHON_HOOK_FILES,
        ),
        ModelLoopErrorTestCase(
            description="macro arguments located in the authored model",
            model_sql="MODEL ();\nSELECT @cents(1 +) AS amount\n",
            expected_message=(
                "Macro arguments of '@cents' in '{model_path}' must use only Python literals, "
                "nested macro calls, and __ref(), __source(), or __seed() references at line 2, "
                "column 17"
            ),
            expected_code="P001",
            files=MACRO_FILES,
        ),
        ModelLoopErrorTestCase(
            description="unary sign over a nested macro returning text",
            model_sql="MODEL ();\nSELECT @cents(-@word()) AS amount\n",
            expected_message=(
                "Macro arguments of '@cents' in '{model_path}' apply unary - to the value of a "
                "nested macro call, which is a str and not a number at line 2, column 16"
            ),
            expected_code="P001",
            files=MACRO_FILES,
        ),
        ModelLoopErrorTestCase(
            description="macro arguments in interpolated SQL stay relative to the call",
            model_sql="MODEL ();\nSELECT '@@region' AS region, @cents(1 +) AS amount\n",
            expected_message=(
                "Macro arguments in '{model_path}' must use only Python literals, nested macro "
                "calls, and __ref(), __source(), or __seed() references at line 1, column 3 of "
                "the '@cents' arguments"
            ),
            expected_code="P001",
            files=MACRO_FILES,
        ),
        ModelLoopErrorTestCase(
            description="unknown enum member",
            model_sql='MODEL ();\nSELECT @enum("order_status").LOST AS status\n',
            expected_message=(
                "Unknown member 'LOST' for enum 'order_status' in '{model_path}'. "
                "Available members: PLACED, SHIPPED"
            ),
            expected_code="P001",
        ),
        ModelLoopErrorTestCase(
            description="unknown constant",
            model_sql='MODEL ();\nSELECT @const("max_items") AS limit_value\n',
            expected_message=(
                "Unknown constant 'max_items' in '{model_path}'. Visible constants: none"
            ),
            expected_code="P001",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_model_when_running_native_model_loop_then_attachment_error_is_raised(
    test_case: ModelLoopErrorTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = copy_project(
        fixtures=(),
        files={
            "sqlbuild_project.toml": 'name = "orders"\nadapter = "duckdb"\n',
            "enums/status.sql": "ENUM (name order_status, members [PLACED, SHIPPED]);\n",
            "models/orders.sql": test_case.model_sql,
        }
        | test_case.files,
        project_dir=tmp_path / "project",
    )

    with pytest.raises(CompileInputError) as raised:
        _ = build_inputs_with_native_loop(project_dir=project_dir, monkeypatch=monkeypatch)

    assert raised.value.message == test_case.expected_message.format(
        model_path=project_dir / "models" / "orders.sql"
    )
    assert raised.value.code == test_case.expected_code


@pytest.mark.parametrize(
    "test_case",
    [
        ImmediateSyntaxErrorTestCase(
            description="query the parser rejects",
            model_sql="MODEL ();\nSELECT FROM WHERE (\n",
            expected_message=(
                "SQL syntax error in model 'orders' ({model_path}): "
                "Expected table name or subquery, got Where"
            ),
            expected_help_fragment="skip SQL analysis for this model",
        ),
        ImmediateSyntaxErrorTestCase(
            description="incremental query with cursor intrinsics the parser rejects",
            model_sql=(
                "MODEL (materialized incremental, incremental_strategy append, cursor order_id,"
                " cursor_type integer);\n"
                "SELECT 1 AS order_id FROM t WHERE order_id >= __cursor_start() AND (\n"
            ),
            expected_message=(
                "SQL syntax error in model 'orders' ({model_path}): Unexpected token: LParen"
            ),
            expected_help_fragment="skip SQL analysis for this model",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unparseable_model_when_validating_immediately_then_syntax_error_is_raised(
    test_case: ImmediateSyntaxErrorTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = copy_project(
        fixtures=(),
        files={
            "sqlbuild_project.toml": 'name = "orders"\nadapter = "duckdb"\n',
            "models/orders.sql": test_case.model_sql,
        },
        project_dir=tmp_path / "project",
    )

    with pytest.raises(CompileInputError) as raised:
        _ = build_inputs_with_native_loop(
            project_dir=project_dir, monkeypatch=monkeypatch, defer_validation=False
        )

    assert raised.value.message == test_case.expected_message.format(
        model_path=project_dir / "models" / "orders.sql"
    )
    assert test_case.expected_help_fragment in (raised.value.help or "")


@pytest.mark.xfail(
    strict=True,
    reason="final gate: compile inputs, assembly, planner and artifacts still build Python objects",
)
@pytest.mark.parametrize(
    "test_case",
    [
        ZeroMaterializationTestCase(
            description="ordinary compile",
            arguments=("compile", "--no-cache"),
            expected_constructions=dict.fromkeys(LEGACY_PROJECT_TYPES, 0),
        ),
        ZeroMaterializationTestCase(
            description="selected compile with a JSON report",
            arguments=("compile", "--no-cache", "--json", "--select", "orders+"),
            expected_constructions=dict.fromkeys(LEGACY_PROJECT_TYPES, 0),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_ordinary_compile_when_compiling_then_no_python_project_is_constructed(
    test_case: ZeroMaterializationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_files(project_dir=tmp_path, files=ORDERS_PROJECT_FILES)
    counts: Counter[str] = count_legacy_constructions(monkeypatch=monkeypatch)

    exit_code: int = main(["--project-dir", str(tmp_path), *test_case.arguments])
    _ = capsys.readouterr()

    assert exit_code == 0
    assert {name: counts[name] for name in LEGACY_PROJECT_TYPES} == (
        test_case.expected_constructions
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ModelPathScopeErrorTestCase(
            description="a folder holding the identity separator is read as an identity",
            model_path="models/a:b/orders.sql",
            expected_message="Unknown qualified identity kind: 'models/a'",
            expected_code="S002",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_path_scope_rejects_when_running_native_model_loop_then_scope_error_is_raised(
    test_case: ModelPathScopeErrorTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = copy_project(
        fixtures=(),
        files={
            "sqlbuild_project.toml": 'name = "orders"\nadapter = "duckdb"\n',
            "enums/status.sql": "ENUM (name order_status, members [PLACED, SHIPPED]);\n",
            test_case.model_path: "MODEL (description 'Orders.');\nSELECT 1 AS order_id\n",
        },
        project_dir=tmp_path / "project",
    )

    with pytest.raises(InvalidQualifiedIdentityError) as raised:
        _ = build_inputs_with_native_loop(project_dir=project_dir, monkeypatch=monkeypatch)

    assert (str(raised.value), raised.value.code) == (
        test_case.expected_message,
        test_case.expected_code,
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
