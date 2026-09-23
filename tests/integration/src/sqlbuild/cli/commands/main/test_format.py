"""Integration coverage for formatting SQL that remains compiler-compatible."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    DescriptionFormatIntegrationTestCase,
    FormatCompileIntegrationTestCase,
    FormatSafetyIntegrationTestCase,
    FormatScopeIntegrationTestCase,
    FormatWarningIntegrationTestCase,
    FromValuesFormatIntegrationTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.helpers import (
    write_from_values_format_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        FormatCompileIntegrationTestCase(
            description="canonical empty input fixture remains compiler-compatible",
            expected_literal="SELECT * FROM __empty_fixture()",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_typed_null_input_when_fixture_formatting_then_canonical_empty_fixture_compiles(
    test_case: FormatCompileIntegrationTestCase,
    tmp_path: Path,
) -> None:
    """Prove formatter output remains valid with uncontrolled-star lint selected."""
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n[rules]\nselect = ["SQBRSQL021"]\n',
        encoding="utf-8",
    )
    models: Path = tmp_path / "models"
    models.mkdir()
    (models / "stg_orders.sql").write_text(
        "MODEL (\n"
        '  description "Staged orders",\n'
        "  contract enforced,\n"
        "  columns (\n"
        "    order_id (type INTEGER, nullable true),\n"
        "    order_label (type VARCHAR, nullable true),\n"
        "  ),\n"
        ");\n\n"
        "SELECT CAST(1 AS INTEGER) AS order_id, CAST('new' AS VARCHAR) AS order_label\n",
        encoding="utf-8",
    )
    (models / "orders.sql").write_text(
        'MODEL (description "Orders");\n\nSELECT order_id, order_label FROM __ref("stg_orders")\n',
        encoding="utf-8",
    )
    test_file: Path = tmp_path / "tests" / "unit" / "test_orders.sql"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "TEST();\n\n"
        "WITH\n"
        "__ref__stg_orders AS (\n"
        "  SELECT\n"
        "    CAST(NULL AS INTEGER) AS order_id,\n"
        "    CAST(NULL AS VARCHAR) AS order_label\n"
        "  WHERE FALSE\n"
        "),\n"
        "__expected__orders AS (SELECT 1 AS order_id, 'new' AS order_label)\n"
        "SELECT 1\n",
        encoding="utf-8",
    )

    format_exit: int = main(["--project-dir", str(tmp_path), "format", "--fixtures-only"])
    compile_exit: int = main(["--project-dir", str(tmp_path), "compile", "--no-cache"])

    assert format_exit == 0
    assert compile_exit == 0
    assert test_case.expected_literal in test_file.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "test_case",
    [
        FormatCompileIntegrationTestCase(
            description="doubled apostrophe remains valid through format and compile",
            expected_literal="'Customer''s order'",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sql_test_string_when_formatting_then_project_still_compiles(
    test_case: FormatCompileIntegrationTestCase,
    tmp_path: Path,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        'MODEL (description "Orders");\nSELECT order_id, order_label FROM __ref("stg_orders")\n',
        encoding="utf-8",
    )
    (model.parent / "stg_orders.sql").write_text(
        'MODEL (description "Staged orders");\n'
        "SELECT 1 AS order_id, 'Customer''s order' AS order_label\n",
        encoding="utf-8",
    )
    test: Path = tmp_path / "tests" / "unit" / "orders.sql"
    test.parent.mkdir(parents=True)
    test.write_text(
        "TEST();\n\nWITH __ref__stg_orders AS ("
        "SELECT 1 AS order_id, 'Customer''s order' AS order_label"
        "), __expected__orders AS ("
        "SELECT 1 AS order_id, 'Customer''s order' AS order_label"
        ")\nSELECT 1\n",
        encoding="utf-8",
    )

    format_exit: int = main(["--project-dir", str(tmp_path), "format"])
    compile_exit: int = main(["--project-dir", str(tmp_path), "compile", "--no-cache"])

    assert format_exit == 0
    assert compile_exit == 0
    assert test_case.expected_literal in test.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "test_case",
    [
        FormatCompileIntegrationTestCase(
            description="table function arguments survive formatter restoration",
            expected_literal='__table_fn("expand_order")(source_orders.order_id)',
        )
    ],
    ids=lambda case: case.description,
)
def test_given_table_function_argument_when_formatting_then_intrinsic_restores_and_compiles(
    test_case: FormatCompileIntegrationTestCase,
    tmp_path: Path,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    function: Path = tmp_path / "functions" / "sql" / "expand_order.sql"
    function.parent.mkdir(parents=True)
    function.write_text(
        """FUNCTION (
  description "Expand one order",
  arguments (order_id INTEGER),
  returns table (order_id INTEGER)
);

SELECT order_id
""",
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "expanded_orders.sql"
    model.parent.mkdir()
    model.write_text(
        'MODEL (description "Expanded orders");\nselect expanded.order_id from orders as '
        'source_orders cross join __table_fn("expand_order")(source_orders.order_id) as expanded\n',
        encoding="utf-8",
    )

    format_exit: int = main(["--project-dir", str(tmp_path), "format"])
    compile_exit: int = main(["--project-dir", str(tmp_path), "compile", "--no-cache"])

    assert format_exit == 0
    assert compile_exit == 0
    formatted: str = model.read_text(encoding="utf-8")
    assert test_case.expected_literal in formatted


@pytest.mark.parametrize(
    "test_case",
    [
        FormatCompileIntegrationTestCase(
            description="explicit null ordering survives format and compile",
            expected_literal="order_id NULLS LAST",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_explicit_null_ordering_when_formatting_then_clause_is_preserved(
    test_case: FormatCompileIntegrationTestCase,
    tmp_path: Path,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        'MODEL (description "Orders");\n'
        'select order_id from __ref("stg_orders") order by order_id nulls last\n',
        encoding="utf-8",
    )
    (model.parent / "stg_orders.sql").write_text(
        'MODEL (description "Staged orders");\nSELECT 1 AS order_id\n',
        encoding="utf-8",
    )

    format_exit: int = main(["--project-dir", str(tmp_path), "format"])
    compile_exit: int = main(["--project-dir", str(tmp_path), "compile", "--no-cache"])

    assert format_exit == 0
    assert compile_exit == 0
    assert test_case.expected_literal in model.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "test_case",
    [
        FormatCompileIntegrationTestCase(
            description="exact contract casts retain authored type spellings",
            expected_literal="CAST('one' AS TEXT) AS order_label",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_exact_contract_casts_when_formatting_then_rule_still_passes(
    test_case: FormatCompileIntegrationTestCase,
    tmp_path: Path,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n[rules]\nselect = ["SQBRCONTRACT105"]\n',
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        "MODEL (\n"
        '  description "Typed orders",\n'
        "  contract enforced,\n"
        "  columns (\n"
        "    order_label (type TEXT)\n"
        "    order_id (type INTEGER)\n"
        "    observed_at (type TIMESTAMP_NTZ)\n"
        "    amount (type NUMERIC(10, 2))\n"
        "  )\n"
        ");\n\n"
        "select cast('one' as TEXT) as order_label, cast(1 as INTEGER) as order_id, "
        "cast('2026-01-01' as TIMESTAMP_NTZ) as observed_at, "
        "cast(12.50 as NUMERIC(10, 2)) as amount\n",
        encoding="utf-8",
    )

    format_exit: int = main(["--project-dir", str(tmp_path), "format"])
    compile_exit: int = main(["--project-dir", str(tmp_path), "compile", "--no-cache"])

    assert format_exit == 0
    assert compile_exit == 0
    formatted: str = model.read_text(encoding="utf-8")
    assert test_case.expected_literal in formatted


@pytest.mark.parametrize(
    "test_case",
    [
        DescriptionFormatIntegrationTestCase(
            description="configured width wraps and compiles model description",
            line_width=60,
            authored_description=(
                "Builds canonical customer records from every available source while retaining "
                "unmatched customers."
            ),
            expected_formatted_description=(
                "Builds canonical customer records from every\n"
                "available source while retaining unmatched customers."
            ),
        ),
        DescriptionFormatIntegrationTestCase(
            description="escaped description content formats and compiles without loss",
            line_width=100,
            authored_description=(
                "Builds order summary.\\nRetains unmatched orders.\\n\\n"
                "Source \\u2192 canonical orders."
            ),
            expected_formatted_description=(
                "Builds order summary. Retains unmatched orders.\n\nSource → canonical orders."
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_description_width_when_formatting_then_wrapped_model_compiles(
    test_case: DescriptionFormatIntegrationTestCase,
    tmp_path: Path,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        f'name = "orders"\nadapter = "duckdb"\n[format]\nline_width = {test_case.line_width}\n',
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        f'MODEL (\n  description "{test_case.authored_description}"\n);\nSELECT 1 AS order_id\n',
        encoding="utf-8",
    )

    format_exit: int = main(["--project-dir", str(tmp_path), "format"])
    compile_exit: int = main(["--project-dir", str(tmp_path), "compile", "--no-cache"])

    assert format_exit == 0
    assert compile_exit == 0
    assert f'description "{test_case.expected_formatted_description}"' in model.read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize(
    "test_case",
    [
        FormatCompileIntegrationTestCase(
            description="schema column remains valid and idempotent",
            expected_literal="SCHEMA (type VARCHAR)",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_schema_column_when_formatting_then_header_remains_valid_and_idempotent(
    test_case: FormatCompileIntegrationTestCase,
    tmp_path: Path,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "catalog"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / "catalog_objects.sql"
    model.parent.mkdir()
    model.write_text(
        "MODEL (\n"
        '  description "Catalog objects.",\n'
        "  materialized table,\n"
        "  columns (\n"
        "    object_id (type INTEGER),\n"
        "    SCHEMA (type VARCHAR),\n"
        "  ),\n"
        ");\n\n"
        "select 1 as object_id, 'analytics' as \"SCHEMA\"\n",
        encoding="utf-8",
    )

    first_exit: int = main(["--project-dir", str(tmp_path), "format"])
    compile_exit: int = main(["--project-dir", str(tmp_path), "compile", "--no-cache"])
    formatted_once: str = model.read_text(encoding="utf-8")
    second_exit: int = main(["--project-dir", str(tmp_path), "format", "--check"])

    assert first_exit == 0
    assert compile_exit == 0
    assert second_exit == 0
    assert formatted_once == model.read_text(encoding="utf-8")
    assert formatted_once.count(test_case.expected_literal) == 1


@pytest.mark.parametrize(
    "test_case",
    [
        FormatSafetyIntegrationTestCase(
            description="unparseable header is untouched",
            authored_sql="MODEL (description);\nselect 1 as order_id\n",
            expected_fault_code="header-parse",
            expected_exit_code=1,
        ),
        FormatSafetyIntegrationTestCase(
            description="unparseable SQL is untouched",
            authored_sql='MODEL (description "Orders."  );\nselect from\n',
            expected_fault_code="format-safety",
            expected_exit_code=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unparseable_file_when_formatting_then_file_is_untouched_and_faults(
    test_case: FormatSafetyIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(test_case.authored_sql, encoding="utf-8")

    exit_code: int = main(["--project-dir", str(tmp_path), "format"])

    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_fault_code in captured.out
    assert model.read_text(encoding="utf-8") == test_case.authored_sql


@pytest.mark.parametrize(
    "test_case",
    [
        FromValuesFormatIntegrationTestCase(
            description="snowflake preserves unparenthesized values relation",
            adapter="snowflake",
            expected_exit_code=0,
            expected_literal="FROM VALUES",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snowflake_from_values_when_formatting_then_form_is_preserved(
    test_case: FromValuesFormatIntegrationTestCase,
    tmp_path: Path,
) -> None:
    project_dir, test_file = write_from_values_format_project(
        tmp_path=tmp_path, adapter=test_case.adapter
    )

    first_exit: int = main(["--project-dir", str(project_dir), "format"])
    formatted_once: str = test_file.read_text(encoding="utf-8")
    second_exit: int = main(["--project-dir", str(project_dir), "format", "--check"])

    assert first_exit == test_case.expected_exit_code
    assert second_exit == test_case.expected_exit_code
    assert test_case.expected_literal in formatted_once
    assert "FROM (VALUES" not in formatted_once
    assert formatted_once == test_file.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "test_case",
    [
        FromValuesFormatIntegrationTestCase(
            description="duckdb values relation remains valid and idempotent",
            adapter="duckdb",
            expected_exit_code=0,
            expected_literal="FROM VALUES",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duckdb_from_values_when_formatting_then_project_compiles(
    test_case: FromValuesFormatIntegrationTestCase,
    tmp_path: Path,
) -> None:
    project_dir, test_file = write_from_values_format_project(
        tmp_path=tmp_path, adapter=test_case.adapter
    )

    first_exit: int = main(["--project-dir", str(project_dir), "format"])
    compile_exit: int = main(["--project-dir", str(project_dir), "compile", "--no-cache"])
    formatted_once: str = test_file.read_text(encoding="utf-8")
    second_exit: int = main(["--project-dir", str(project_dir), "format", "--check"])

    assert first_exit == test_case.expected_exit_code
    assert compile_exit == test_case.expected_exit_code
    assert second_exit == test_case.expected_exit_code
    assert test_case.expected_literal in formatted_once
    assert formatted_once == test_file.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "test_case",
    [
        FormatScopeIntegrationTestCase(
            description="default exclusions and path selectors share format scope",
            expected_exclude_exit=1,
            expected_selected_model_exit=0,
            expected_path_with_exclude_exit=1,
            expected_exclude_path_exit=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_format_selectors_when_scoping_then_paths_and_default_exclusions_are_consistent(
    test_case: FormatScopeIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    models: Path = tmp_path / "models"
    models.mkdir()
    (models / "customers.sql").write_text(
        "MODEL (materialized table, columns (customer_id (type INTEGER),));\n"
        "SELECT\n"
        "  1 AS customer_id\n",
        encoding="utf-8",
    )
    (models / "orders.sql").write_text(
        'MODEL (description "Orders.", materialized table, '
        "columns (order_id (type INTEGER),));\n"
        "SELECT\n"
        "  customer_id AS order_id\n"
        'FROM __ref("customers")\n',
        encoding="utf-8",
    )
    test_file: Path = tmp_path / "tests" / "unit" / "test_orders.sql"
    test_file.parent.mkdir(parents=True)
    unformatted_test: str = (
        'TEST (name "orders_returns_one_row");\n\n'
        "WITH __ref__customers AS (\n    SELECT 1 AS customer_id\n),\n"
        "__expected__orders AS (\n    SELECT 1 AS order_id\n)\nSELECT 1\n"
    )
    test_file.write_text(unformatted_test, encoding="utf-8")

    exclude_exit: int = main(
        ["--project-dir", str(tmp_path), "format", "--check", "--exclude", "customers"]
    )
    exclude_output: str = capsys.readouterr().err
    selected_model_exit: int = main(
        ["--project-dir", str(tmp_path), "format", "--check", "--select", "orders"]
    )
    selected_model_output: str = capsys.readouterr().err
    path_with_exclude_exit: int = main(
        [
            "--project-dir",
            str(tmp_path),
            "format",
            "--check",
            "--select",
            "path:tests",
            "--exclude",
            "orders",
        ]
    )
    path_with_exclude_output: str = capsys.readouterr().err
    exclude_path_exit: int = main(
        ["--project-dir", str(tmp_path), "format", "--check", "--exclude", "path:tests"]
    )
    exclude_path_output: str = capsys.readouterr().err

    assert exclude_exit == test_case.expected_exclude_exit
    assert "2 files checked" in exclude_output
    assert selected_model_exit == test_case.expected_selected_model_exit
    assert "1 files checked" in selected_model_output
    assert path_with_exclude_exit == test_case.expected_path_with_exclude_exit
    assert "1 files checked" in path_with_exclude_output
    assert exclude_path_exit == test_case.expected_exclude_path_exit
    assert "2 files checked" in exclude_path_output
    assert test_file.read_text(encoding="utf-8") == unformatted_test


@pytest.mark.parametrize(
    "test_case",
    [
        FormatWarningIntegrationTestCase(
            description="missing model description warns without failing format",
            expected_exit_code=0,
            expected_code="description-present",
            expected_severity="warning",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_description_when_formatting_then_warning_does_not_fail(
    test_case: FormatWarningIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text("MODEL (materialized table);\nSELECT 1 AS order_id\n", encoding="utf-8")

    write_exit: int = main(["--project-dir", str(tmp_path), "format"])
    _ = capsys.readouterr()
    text_exit: int = main(["--project-dir", str(tmp_path), "format", "--check"])
    text_output: str = capsys.readouterr().out
    json_exit: int = main(["--project-dir", str(tmp_path), "format", "--check", "--json"])
    payload: dict[str, object] = json.loads(capsys.readouterr().out)

    assert write_exit == test_case.expected_exit_code
    assert text_exit == test_case.expected_exit_code
    assert f"warning[{test_case.expected_code}]" in text_output
    assert json_exit == test_case.expected_exit_code
    assert payload["faults"] == 0
    assert payload["warnings"] == 1
    violations: object = payload["violations"]
    assert isinstance(violations, list)
    assert violations[0]["code"] == test_case.expected_code
    assert violations[0]["severity"] == test_case.expected_severity
