from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import (
    MacroDeclarationContextErrorTestCase,
    MacroDeclarationResourceTestCase,
)
from tests.integration.src.sqlbuild.compiler.pipeline.helpers import (
    run_compile_pipeline_for_project,
)


@pytest.mark.parametrize(
    "test_case",
    (
        MacroDeclarationResourceTestCase(
            description="models tests and audits receive caller-visible constants",
            expected_model_sql_fragment="SELECT 2 AS minimum_quantity",
            expected_test_sql_fragment="SELECT 2 AS minimum_quantity",
            expected_audit_sql_fragment="minimum_quantity < 2",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_macro_context_declarations_when_compiling_resources_then_all_expand(
    test_case: MacroDeclarationResourceTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": (
                'name = "demo"\nadapter = "duckdb"\n\n[settings]\nsql_analysis = false\n'
            ),
            "constants/policy.sql": "CONSTANT (name minimum_quantity, value 2);\n",
            "macros/policy.py": (
                "def minimum_quantity(ctx) -> str:\n"
                "    return str(ctx.constants['minimum_quantity'])\n"
            ),
            "models/summary.sql": (
                "MODEL (materialized view, audits [minimum_quantity]);\n\n"
                "SELECT @minimum_quantity() AS minimum_quantity"
            ),
            "tests/unit/summary.sql": (
                "TEST (mode macro);\n\nWITH\n__macro_actual__ AS (\n"
                "  SELECT @minimum_quantity() AS minimum_quantity\n),\n"
                "__macro_expected__ AS (\n  SELECT 2 AS minimum_quantity\n)\nSELECT 1"
            ),
            "audits/generic/minimum_quantity.sql": (
                'AUDIT ();\n\nSELECT * FROM __ref("@model") '
                "WHERE minimum_quantity < @minimum_quantity()"
            ),
        },
    )

    result: CompilePipelineResult = run_compile_pipeline_for_project(
        project_dir=tmp_path, adapter=DuckDbAdapter()
    )

    assert test_case.expected_model_sql_fragment in result.project.models[0].query_sql
    assert test_case.expected_test_sql_fragment in result.project.sql_tests[0].sql_body
    assert test_case.expected_audit_sql_fragment in result.project.audits[0].sql_body


@pytest.mark.parametrize(
    "test_case",
    (
        MacroDeclarationContextErrorTestCase(
            description="sibling private constant remains inaccessible",
            project_files={
                "sqlbuild_project.toml": 'name = "demo"\nadapter = "duckdb"\n',
                "models/orders/_constants/policy.sql": (
                    "CONSTANT (name minimum_quantity, value 2);\n"
                ),
                "macros/policy.py": (
                    "def minimum_quantity(ctx) -> str:\n"
                    "    return str(ctx.constants['minimum_quantity'])\n"
                ),
                "models/products/summary.sql": (
                    "MODEL (materialized view);\n\nSELECT @minimum_quantity() AS minimum_quantity"
                ),
            },
            expected_error_fragment="Constant 'minimum_quantity'.*is inaccessible",
        ),
        MacroDeclarationContextErrorTestCase(
            description="unknown constant reports visible alternatives",
            project_files={
                "sqlbuild_project.toml": 'name = "demo"\nadapter = "duckdb"\n',
                "models/_constants/policy.sql": ("CONSTANT (name minimum_quantity, value 2);\n"),
                "models/_macros/policy.py": (
                    "def missing_quantity(ctx) -> str:\n"
                    "    return str(ctx.constants['maximum_quantity'])\n"
                ),
                "models/summary.sql": (
                    "MODEL (materialized view);\n\nSELECT @missing_quantity() AS maximum_quantity"
                ),
            },
            expected_error_fragment=(
                "Unknown constant 'maximum_quantity'.*Visible constants: minimum_quantity"
            ),
        ),
        MacroDeclarationContextErrorTestCase(
            description="unknown enum member reports available alternatives",
            project_files={
                "sqlbuild_project.toml": 'name = "demo"\nadapter = "duckdb"\n',
                "models/_enums/status.sql": (
                    "ENUM (name order_status, members [ACTIVE, PAUSED]);\n"
                ),
                "models/_macros/policy.py": (
                    "def missing_status(ctx) -> str:\n"
                    "    return str(ctx.enums['order_status']['CLOSED'])\n"
                ),
                "models/summary.sql": (
                    "MODEL (materialized view);\n\nSELECT @missing_status() AS status"
                ),
            },
            expected_error_fragment=(
                "Unknown member 'CLOSED' for enum 'order_status'.*Available members: ACTIVE, PAUSED"
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unavailable_declaration_when_macro_reads_context_then_compile_fails(
    test_case: MacroDeclarationContextErrorTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        run_compile_pipeline_for_project(project_dir=tmp_path, adapter=DuckDbAdapter())
