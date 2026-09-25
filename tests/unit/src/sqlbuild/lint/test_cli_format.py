"""Behavior tests for the source-rewriting format command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from _pytest.capture import CaptureResult

import sqlbuild._native as native_module
import sqlbuild.cli.commands._helpers.lint.selection as lint_selection_module
import sqlbuild.compiler.planner._helpers.sql_tests.fixture_formatting as fixture_formatting_module
from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.unit.src.sqlbuild.lint._test_types import (
    FormatCliTestCase,
    FormatSelectionWorkTestCase,
)
from tests.unit.src.sqlbuild.lint.helpers import write_fixture_format_project

PROJECT_TOML: str = 'name = "demo"\nadapter = "duckdb"\n'


@pytest.mark.parametrize(
    "test_case",
    [
        FormatCliTestCase("writes formatted SQL", (), 0, "Formatted files:", True),
        FormatCliTestCase("check reports changes", ("--check",), 1, "Would format files:"),
        FormatCliTestCase("diff prints without writing", ("--diff",), 0, "+SELECT"),
    ],
    ids=lambda case: case.description,
)
def test_given_unformatted_sql_when_formatting_then_mode_controls_writes(
    test_case: FormatCliTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    original: str = 'MODEL (description "Orders");\nselect order_id,status from orders\n'
    model.write_text(original, encoding="utf-8")

    exit_code: int = main(["--project-dir", str(tmp_path), "format", *test_case.arguments])

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_fragment in capsys.readouterr().out
    formatted: str = model.read_text(encoding="utf-8")
    assert (formatted != original) is test_case.expected_writes


@pytest.mark.parametrize(
    "test_case",
    [FormatCliTestCase("legacy lint config is rejected", (), 1, "unsupported legacy")],
    ids=lambda case: case.description,
)
def test_given_legacy_lint_configuration_when_formatting_then_it_is_rejected(
    test_case: FormatCliTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        f'{PROJECT_TOML}\n[lint]\nselect = ["SQBRSQL"]\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text('MODEL (description "Orders");\nSELECT 1 AS order_id\n', encoding="utf-8")

    exit_code: int = main(["--project-dir", str(tmp_path), "compile"])

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_fragment in capsys.readouterr().err


@pytest.mark.parametrize(
    "test_case",
    [FormatCliTestCase("format does not enforce unselected Rules", (), 0, "SQBRSQL004")],
    ids=lambda case: case.description,
)
def test_given_unselected_sql_rule_finding_when_formatting_then_rule_is_not_enforced(
    test_case: FormatCliTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        'MODEL (description "Orders");\nSELECT order_id FROM orders LIMIT 1\n',
        encoding="utf-8",
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "format"])

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_fragment not in capsys.readouterr().out


@pytest.mark.parametrize(
    "test_case",
    [
        FormatCliTestCase(
            "typed fixture null diff",
            ("--diff",),
            0,
            "test_orders.sql",
            False,
        ),
        FormatCliTestCase(
            "typed fixture null apply",
            (),
            0,
            "Formatted files:",
            True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_redundant_typed_fixture_null_when_formatting_then_safe_fix_uses_contract(
    test_case: FormatCliTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    staging_model: Path = tmp_path / "models" / "stg_orders.sql"
    staging_model.parent.mkdir()
    staging_model.write_text(
        "MODEL (\n"
        '  description "Staged orders",\n'
        "  contract enforced,\n"
        "  columns (\n"
        "    order_id (type INTEGER, nullable false),\n"
        "    status (type VARCHAR, nullable true),\n"
        "  ),\n"
        ");\n\n"
        "SELECT 1 AS order_id, CAST(NULL AS VARCHAR) AS status\n",
        encoding="utf-8",
    )
    (tmp_path / "models" / "orders.sql").write_text(
        'MODEL (description "Orders");\n\nSELECT order_id, status FROM __ref("stg_orders")\n',
        encoding="utf-8",
    )
    test_file: Path = tmp_path / "tests" / "unit" / "test_orders.sql"
    test_file.parent.mkdir(parents=True)
    original: str = (
        "TEST();\n\n"
        "WITH\n"
        "helper AS (SELECT '__ref__stg_orders AS (keep)' AS label),\n"
        "__ref__stg_orders AS (\n"
        "    SELECT\n"
        "        1 AS order_id,\n"
        "        CAST(NULL AS VARCHAR(100)) AS status\n"
        "),\n"
        "__expected__orders AS (\n"
        "    SELECT 1 AS order_id, CAST(NULL AS VARCHAR) AS status\n"
        ")\n"
        "SELECT 1\n"
    )
    test_file.write_text(original, encoding="utf-8")

    exit_code: int = main(["--project-dir", str(tmp_path), "format", *test_case.arguments])

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_fragment in capsys.readouterr().out
    formatted: str = test_file.read_text(encoding="utf-8")
    fixture_prefix, expected_suffix = formatted.split("__expected__orders", maxsplit=1)
    assert (
        "CAST(NULL AS VARCHAR(100)) AS status" not in fixture_prefix
    ) is test_case.expected_writes
    assert "CAST(NULL AS VARCHAR) AS status" in expected_suffix
    assert "'__ref__stg_orders AS (keep)'" in formatted


@pytest.mark.parametrize(
    "test_case",
    [FormatCliTestCase("all-null empty fixture", (), 0, "__empty_fixture()")],
    ids=lambda case: case.description,
)
def test_given_all_null_empty_fixture_when_formatting_then_uses_empty_fixture_marker(
    test_case: FormatCliTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        "MODEL (\n"
        '  description "Orders",\n'
        "  contract enforced,\n"
        "  columns (\n"
        "    order_id (type INTEGER, nullable false),\n"
        "    status (type VARCHAR),\n"
        "  ),\n"
        ");\n\n"
        "SELECT 1 AS order_id, 'open' AS status\n",
        encoding="utf-8",
    )
    test_file: Path = tmp_path / "tests" / "unit" / "test_orders.sql"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "TEST();\n\n"
        "WITH\n"
        "__ref__orders AS (\n"
        "  SELECT\n"
        "    CAST(NULL AS INTEGER) AS order_id,\n"
        "    CAST(NULL AS VARCHAR) AS status\n"
        "  WHERE FALSE\n"
        "),\n"
        "__expected__orders AS (SELECT 1 AS order_id, 'open' AS status)\n"
        "SELECT 1\n",
        encoding="utf-8",
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "format"])

    assert exit_code == test_case.expected_exit_code
    assert "Formatted files:" in capsys.readouterr().out
    formatted: str = test_file.read_text(encoding="utf-8")
    assert test_case.expected_fragment in formatted
    assert "__ref__orders AS (\n  SELECT\n    *\n  FROM __empty_fixture()\n)" in formatted
    assert "CAST(NULL" not in formatted.split("__expected__orders", maxsplit=1)[0]


@pytest.mark.parametrize(
    "test_case",
    [FormatCliTestCase("uncompilable project fallback", (), 0, "CAST(NULL AS INTEGER)")],
    ids=lambda case: case.description,
)
def test_given_uncompilable_project_with_fixture_null_when_formatting_then_formats_without_autofix(
    test_case: FormatCliTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        'MODEL (description "Orders");\n\nselect * from __ref("missing_orders")\n',
        encoding="utf-8",
    )
    test_file: Path = tmp_path / "tests" / "unit" / "test_orders.sql"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "TEST();\n\n"
        "WITH\n"
        "__ref__missing_orders AS (\n"
        "  SELECT CAST(NULL AS INTEGER) AS order_id WHERE FALSE\n"
        "),\n"
        "__expected__orders AS (SELECT 1 AS order_id)\n"
        "SELECT 1\n",
        encoding="utf-8",
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "format"])

    assert exit_code == test_case.expected_exit_code
    assert "Formatted files:" in capsys.readouterr().out
    formatted: str = test_file.read_text(encoding="utf-8")
    assert test_case.expected_fragment in formatted
    assert "CAST(NULL AS INTEGER) AS order_id" in formatted
    assert "WITH __ref__missing_orders AS" in formatted


@pytest.mark.parametrize(
    "test_case",
    [FormatCliTestCase("non-null expression", (), 0, "IS NULL OR (")],
    ids=lambda case: case.description,
)
def test_given_typed_null_inside_boolean_expression_when_formatting_then_expression_is_preserved(
    test_case: FormatCliTestCase,
    tmp_path: Path,
) -> None:
    test_file: Path = write_fixture_format_project(
        tmp_path=tmp_path,
        fixture_sql=(
            "\n  SELECT\n    1 AS id,\n    CAST(NULL AS BOOLEAN) IS NULL OR (TRUE) AS flag\n"
        ),
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "format"])

    assert exit_code == test_case.expected_exit_code
    formatted: str = test_file.read_text(encoding="utf-8")
    assert test_case.expected_fragment in formatted
    assert "CAST(NULL AS BOOLEAN) IS NULL OR (" in formatted
    assert ") AS flag" in formatted


@pytest.mark.parametrize(
    "test_case",
    [FormatCliTestCase("union branches", (), 0, "UNION ALL")],
    ids=lambda case: case.description,
)
def test_given_union_fixture_when_formatting_then_branch_shapes_are_preserved(
    test_case: FormatCliTestCase,
    tmp_path: Path,
) -> None:
    test_file: Path = write_fixture_format_project(
        tmp_path=tmp_path,
        fixture_sql=(
            "\n  SELECT\n"
            "    1 AS id,\n"
            "    CAST(NULL AS BOOLEAN) AS flag\n"
            "  UNION ALL\n"
            "  SELECT 2 AS id, TRUE AS flag\n"
        ),
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "format"])

    assert exit_code == test_case.expected_exit_code
    formatted: str = test_file.read_text(encoding="utf-8")
    assert test_case.expected_fragment in formatted
    assert "CAST(NULL AS BOOLEAN) AS flag" in formatted
    assert "UNION ALL" in formatted


@pytest.mark.parametrize(
    "test_case",
    [FormatCliTestCase("non-prefix fixture", (), 0, "CAST(NULL AS VARCHAR) AS status")],
    ids=lambda case: case.description,
)
def test_given_middle_typed_null_when_formatting_then_star_safe_prefix_is_preserved(
    test_case: FormatCliTestCase,
    tmp_path: Path,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        PROJECT_TOML + '\n[defaults]\ncontract = "enforced"\n',
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        'MODEL (description "Orders", columns ('
        "order_id (type INTEGER), status (type VARCHAR), amount (type DOUBLE)));\n"
        "SELECT 1 AS order_id, 'open' AS status, 1.0 AS amount\n",
        encoding="utf-8",
    )
    test_file: Path = tmp_path / "tests" / "unit" / "test_orders.sql"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "TEST();\n\n"
        "WITH __ref__orders AS (\n"
        "  SELECT\n"
        "    1 AS order_id,\n"
        "    CAST(NULL AS VARCHAR) AS status,\n"
        "    1.0 AS amount\n"
        "), __expected__orders AS (SELECT 1 AS order_id)\n"
        "SELECT 1\n",
        encoding="utf-8",
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "format"])

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_fragment in test_file.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "test_case",
    [FormatCliTestCase("empty explicit selector", ("--select", " "), 1, "matched no SQL files")],
    ids=lambda case: case.description,
)
def test_given_empty_explicit_selector_when_formatting_then_no_files_are_modified(
    test_case: FormatCliTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    original: str = 'MODEL (description "Orders");\nselect 1 as order_id\n'
    model.write_text(original, encoding="utf-8")

    exit_code: int = main(["--project-dir", str(tmp_path), "format", *test_case.arguments])

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_fragment in capsys.readouterr().err
    assert model.read_text(encoding="utf-8") == original


@pytest.mark.parametrize(
    "test_case",
    [FormatCliTestCase("SQL analysis disabled", (), 0, "CAST(NULL AS BOOLEAN)")],
    ids=lambda case: case.description,
)
def test_given_sql_analysis_disabled_when_formatting_then_fixture_null_is_preserved(
    test_case: FormatCliTestCase,
    tmp_path: Path,
) -> None:
    test_file: Path = write_fixture_format_project(
        tmp_path=tmp_path,
        fixture_sql=("\n  SELECT\n    1 AS id,\n    CAST(NULL AS BOOLEAN) AS flag\n"),
        project_toml=PROJECT_TOML + "\n[settings]\nsql_analysis = false\n",
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "format"])

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_fragment in test_file.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "test_case",
    [FormatCliTestCase("macro-expanded fixture", (), 0, "@mock_rows()")],
    ids=lambda case: case.description,
)
def test_given_macro_expanded_fixture_when_formatting_then_authored_source_is_not_rewritten(
    test_case: FormatCliTestCase,
    tmp_path: Path,
) -> None:
    test_file: Path = write_fixture_format_project(
        tmp_path=tmp_path,
        fixture_sql="@mock_rows()",
    )
    macro_file: Path = tmp_path / "macros" / "rows.py"
    macro_file.parent.mkdir()
    macro_file.write_text(
        "def mock_rows() -> str:\n"
        "    return (\n"
        '        "SELECT\\n"\n'
        '        "    1 AS id,\\n"\n'
        '        "    CAST(NULL AS BOOLEAN) AS flag"\n'
        "    )\n",
        encoding="utf-8",
    )
    authored: str = test_file.read_text(encoding="utf-8")
    test_file.write_text(
        authored.replace(
            "WITH\n",
            "WITH\n"
            "helper AS (\n"
            "  SELECT 'SELECT\n"
            "    1 AS id,\n"
            "    CAST(NULL AS BOOLEAN) AS flag' AS fixture_text\n"
            "),\n",
            1,
        ),
        encoding="utf-8",
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "format"])

    assert exit_code == test_case.expected_exit_code
    formatted: str = test_file.read_text(encoding="utf-8")
    assert test_case.expected_fragment in formatted
    assert "CAST(NULL AS BOOLEAN) AS flag' AS fixture_text" in formatted


@pytest.mark.parametrize(
    "test_case",
    [
        FormatCliTestCase(
            description="fixture-only formatting preserves unrelated SQL layout",
            arguments=("--fixtures-only", "--select", "path:tests"),
            expected_exit_code=0,
            expected_fragment="__expected__rows AS (select 1 AS id, TRUE AS flag)",
            expected_writes=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_fixture_only_mode_when_formatting_then_only_fixture_nulls_are_rewritten(
    test_case: FormatCliTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_file: Path = write_fixture_format_project(
        tmp_path=tmp_path,
        fixture_sql=("\n  SELECT\n    1 AS id,\n    CAST(NULL AS BOOLEAN) AS flag\n"),
    )
    authored: str = test_file.read_text(encoding="utf-8").replace(
        "__expected__rows AS (SELECT 1 AS id, TRUE AS flag)",
        "__expected__rows AS (select 1 AS id, TRUE AS flag)",
    )
    test_file.write_text(authored, encoding="utf-8")
    native_format: Mock = Mock(wraps=native_module.format_sql_batch_json)
    monkeypatch.setattr(native_module, "format_sql_batch_json", native_format)

    exit_code: int = main(["--project-dir", str(tmp_path), "format", *test_case.arguments])

    formatted: str = test_file.read_text(encoding="utf-8")
    assert exit_code == test_case.expected_exit_code
    assert "CAST(NULL AS BOOLEAN)" not in formatted
    assert test_case.expected_fragment in formatted
    assert native_format.call_count == 0


@pytest.mark.parametrize(
    "test_case",
    [
        FormatSelectionWorkTestCase(
            description="selected test path bounds fixture parsing and native formatting",
            selected_file_count=2,
            expected_fixture_parse_count=1,
            expected_native_batch_count=1,
            expected_native_request_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_test_path_selector_when_formatting_then_work_is_bounded_to_selected_files(
    test_case: FormatSelectionWorkTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        PROJECT_TOML + '\n[defaults]\ncontract = "enforced"\n',
        encoding="utf-8",
    )
    model_dir: Path = tmp_path / "models"
    model_dir.mkdir()
    model_dir.joinpath("stg_orders.sql").write_text(
        "MODEL (columns (order_id (type INTEGER), status (type VARCHAR)));\n"
        "SELECT 1 AS order_id, 'open' AS status\n",
        encoding="utf-8",
    )
    model_dir.joinpath("orders.sql").write_text(
        "MODEL (columns (order_id (type INTEGER), status (type VARCHAR)));\n"
        'SELECT order_id, status FROM __ref("stg_orders")\n',
        encoding="utf-8",
    )
    fixture_sql: str = (
        "TEST();\n\n"
        "WITH __ref__stg_orders AS (\n"
        "  SELECT\n"
        "    1 AS order_id,\n"
        "    CAST(NULL AS VARCHAR) AS status\n"
        "), __expected__orders AS (\n"
        "  SELECT 1 AS order_id, NULL AS status\n"
        ")\n"
        "SELECT 1\n"
    )
    selected_dir: Path = tmp_path / "tests" / "unit" / "orders"
    selected_dir.mkdir(parents=True)
    selected_files: tuple[Path, ...] = (
        selected_dir / "test_first.sql",
        selected_dir / "test_second.sql",
    )
    selected_files[0].write_text(fixture_sql, encoding="utf-8")
    selected_files[1].write_text(
        fixture_sql.replace(
            "    1 AS order_id,\n    CAST(NULL AS VARCHAR) AS status\n",
            "    1 AS order_id\n",
        ),
        encoding="utf-8",
    )
    unselected_file: Path = tmp_path / "tests" / "unit" / "customers" / "test_other.sql"
    unselected_file.parent.mkdir()
    unselected_file.write_text(fixture_sql, encoding="utf-8")
    fixture_parse: Mock = Mock(wraps=fixture_formatting_module.SqlTestCteExtractor.extract)
    native_format: Mock = Mock(wraps=native_module.format_sql_batch_json)
    full_discovery: Mock = Mock(side_effect=AssertionError("full discovery must not run"))
    project_graph: Mock = Mock(side_effect=AssertionError("project graph must not build"))
    monkeypatch.setattr(fixture_formatting_module.SqlTestCteExtractor, "extract", fixture_parse)
    monkeypatch.setattr(native_module, "format_sql_batch_json", native_format)
    monkeypatch.setattr(lint_selection_module, "discover_project_inputs", full_discovery)
    monkeypatch.setattr(lint_selection_module, "build_project_graph", project_graph)

    exit_code: int = main(
        [
            "--project-dir",
            str(tmp_path),
            "format",
            "--select",
            "path:tests/unit/orders",
        ]
    )

    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == 0
    assert f"{test_case.selected_file_count} files checked" in captured.err
    assert fixture_parse.call_count == test_case.expected_fixture_parse_count
    assert native_format.call_count == test_case.expected_native_batch_count
    native_requests: object = json.loads(native_format.call_args.args[0])
    assert isinstance(native_requests, list)
    assert len(native_requests) == test_case.expected_native_request_count
    assert full_discovery.call_count == 0
    assert project_graph.call_count == 0
    assert all(
        "CAST(NULL AS VARCHAR)" not in path.read_text(encoding="utf-8") for path in selected_files
    )
    assert "CAST(NULL AS VARCHAR)" in unselected_file.read_text(encoding="utf-8")
