"""Behavior tests for the source-rewriting format command."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.unit.src.sqlbuild.lint._test_types import FormatCliTestCase
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
    [FormatCliTestCase("all-null empty fixture", (), 0, "__EMPTY_FIXTURE()")],
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
    assert "__ref__orders AS (\n  SELECT\n    *\n  FROM __EMPTY_FIXTURE()\n)" in formatted
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
