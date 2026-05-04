from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.helpers.assembly import assemble_compiled_project
from sqlbuild.compiler.compile.main.build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledProject,
    CompileProjectInputs,
)
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
    CompiledResourceType,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from tests.unit.src.sqlbuild.compiler.compile._test_helpers import (
    base_repo_files,
)
from tests.unit.src.sqlbuild.compiler.compile.helpers._test_types import (
    AssembleCompiledProjectTestCase,
)

ASSEMBLE_COMPILED_PROJECT_TEST_CASES: list[AssembleCompiledProjectTestCase] = [
    AssembleCompiledProjectTestCase(
        description="assembles models sources seeds audits and tests into compiled project",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb

settings:
  default_audit_severity: warn

defaults:
  materialized: table
  schema: analytics
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect * from __source('raw_orders')\n",
            "models/staging/schema.yml": """
models:
  - name: orders
    columns:
      - name: order_id
        type: VARCHAR
    audits:
      - not_null:
          column: order_id
""".strip()
            + "\n",
            "sources/raw.yml": """
sources:
  - name: raw_orders
    schema: public
    table: orders
""".strip()
            + "\n",
            "seeds/schema.yml": """
seeds:
  - name: country_codes
    columns:
      - name: code
        type: VARCHAR
""".strip()
            + "\n",
            "seeds/country_codes.csv": "code\nUS\n",
            "audits/generic/not_null.sql": "AUDIT ();\n\n"
            "SELECT @column FROM __ref('@model') WHERE @column IS NULL\n",
            "tests/orders_test.sql": """
TEST ();

WITH
__ref__orders AS (SELECT 'x' AS order_id),
__source__raw_orders AS (SELECT 'x' AS order_id),
__expected__orders AS (SELECT 'x' AS order_id)
SELECT 1
""".strip()
            + "\n",
        },
        expected_model_names=("orders",),
        expected_model_deps=(
            (CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name="raw_orders"),),
        ),
        expected_model_target_names=("orders",),
        expected_model_target_schemas=("analytics",),
        expected_source_names=("raw_orders",),
        expected_seed_names=("country_codes",),
        expected_seed_target_schemas=("analytics",),
        expected_seed_target_databases=(None,),
        expected_seed_target_qualified_names=(None,),
        expected_audit_names=("not_null",),
        expected_audit_scope_deps=(
            (CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),),
        ),
        expected_audit_attached_target_kinds=(AttachedAuditTargetKind.MODEL,),
        expected_test_names=("orders_test",),
        expected_test_scope_deps=(
            (CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),),
        ),
        expected_test_expected_model_names=(("orders",),),
    ),
    AssembleCompiledProjectTestCase(
        description="assembles seed targets using local environment database templates",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb
default_environment: dev

vars:
  project: reporting

defaults:
  schema: analytics

environments:
  dev:
    database: "${ENV:TARGET_DB}_${project}"
    schema: seeds_${project}
""".strip()
            + "\n",
            "sqlbuild_local.yml": """
environments:
  dev:
    database: "${ENV:LOCAL_TARGET_DB}_${project}"
""".strip()
            + "\n",
            "seeds/schema.yml": """
seeds:
  - name: country_codes
    columns:
      - name: code
        type: VARCHAR
""".strip()
            + "\n",
            "seeds/country_codes.csv": "code\nUS\n",
        },
        expected_model_names=(),
        expected_model_deps=(),
        expected_model_target_names=(),
        expected_model_target_schemas=(),
        expected_source_names=(),
        expected_seed_names=("country_codes",),
        expected_seed_target_schemas=("seeds_reporting",),
        expected_seed_target_databases=("local_reportingdb_reporting",),
        expected_seed_target_qualified_names=(None,),
        expected_audit_names=(),
        expected_audit_scope_deps=(),
        expected_test_names=(),
        expected_test_scope_deps=(),
        expected_test_expected_model_names=(),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ASSEMBLE_COMPILED_PROJECT_TEST_CASES,
    ids=[case.description for case in ASSEMBLE_COMPILED_PROJECT_TEST_CASES],
)
def test_given_compile_inputs_when_assembling_compiled_project_then_returns_expected_resources(
    test_case: AssembleCompiledProjectTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    monkeypatch.setenv("TARGET_DB", "projectdb")
    monkeypatch.setenv("LOCAL_TARGET_DB", "local_reportingdb")
    write_repo_files(tmp_path, test_case.repo_files)
    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    compile_inputs: CompileProjectInputs = build_compile_inputs(discovered, run_id="test_run_id")
    compiled: CompiledProject = assemble_compiled_project(compile_inputs)

    assert tuple(m.name for m in compiled.models) == test_case.expected_model_names
    assert tuple(m.deps for m in compiled.models) == test_case.expected_model_deps
    assert tuple(m.target.name for m in compiled.models) == test_case.expected_model_target_names
    assert (
        tuple(m.target.schema for m in compiled.models) == test_case.expected_model_target_schemas
    )
    assert tuple(s.name for s in compiled.sources) == test_case.expected_source_names
    assert tuple(s.name for s in compiled.seeds) == test_case.expected_seed_names
    assert tuple(s.target.schema for s in compiled.seeds) == test_case.expected_seed_target_schemas
    assert (
        tuple(s.target.database for s in compiled.seeds) == test_case.expected_seed_target_databases
    )
    assert (
        tuple(s.target.qualified_name for s in compiled.seeds)
        == test_case.expected_seed_target_qualified_names
    )
    assert tuple(a.name for a in compiled.audits) == test_case.expected_audit_names
    assert tuple(a.scope_deps for a in compiled.audits) == test_case.expected_audit_scope_deps
    assert (
        tuple(a.attached_target_kind for a in compiled.audits)
        == test_case.expected_audit_attached_target_kinds
    )
    assert tuple(t.name for t in compiled.sql_tests) == test_case.expected_test_names
    assert tuple(t.scope_deps for t in compiled.sql_tests) == test_case.expected_test_scope_deps
    assert (
        tuple(t.expected_model_names for t in compiled.sql_tests)
        == test_case.expected_test_expected_model_names
    )
