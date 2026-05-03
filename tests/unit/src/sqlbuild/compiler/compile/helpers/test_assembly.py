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
from sqlbuild.compiler.discovery.main import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from tests.unit.src.sqlbuild.compiler.compile._test_helpers import (
    base_repo_files,
)
from tests.unit.src.sqlbuild.compiler.compile.helpers._test_types import (
    AssembleCompiledProjectTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
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
    ],
    ids=["assembles models sources seeds audits and tests into compiled project"],
)
def test_given_compile_inputs_when_assembling_compiled_project_then_returns_expected_resources(
    test_case: AssembleCompiledProjectTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
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
