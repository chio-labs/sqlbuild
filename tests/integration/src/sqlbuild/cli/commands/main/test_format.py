"""Integration coverage for formatting SQL that remains compiler-compatible."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    DescriptionFormatIntegrationTestCase,
    FormatCompileIntegrationTestCase,
)


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
        )
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
