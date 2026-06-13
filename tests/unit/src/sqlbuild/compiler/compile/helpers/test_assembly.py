from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.helpers.assembly import assemble_compiled_project
from sqlbuild.compiler.compile.main.build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models.core import (
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
from tests.unit.src.sqlbuild.compiler.compile.helpers.helpers import (
    compiled_sql_test_expected_model_names,
    compiled_sql_test_tested_resource_names,
)

ASSEMBLE_COMPILED_PROJECT_TEST_CASES: list[AssembleCompiledProjectTestCase] = [
    AssembleCompiledProjectTestCase(
        description="assembles models sources seeds audits and tests into compiled project",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.toml": """
name = "demo"
adapter = "duckdb"

[settings]
default_audit_severity = "warn"

[defaults]
materialized = "table"
schema = "analytics"
""".strip()
            + "\n",
            "models/staging/orders.sql": """
MODEL (
  columns (
    order_id (type VARCHAR),
  ),
  audits [not_null (column order_id, always_run true)],
);

select * from __source('raw_orders')
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
            "tests/unit/orders_test.sql": """
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
        expected_source_databases=(None,),
        expected_source_schemas=("public",),
        expected_seed_names=("country_codes",),
        expected_seed_target_schemas=("analytics",),
        expected_seed_target_databases=(None,),
        expected_seed_target_qualified_names=(None,),
        expected_audit_names=("not_null",),
        expected_audit_scope_deps=(
            (CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),),
        ),
        expected_audit_attached_target_kinds=(AttachedAuditTargetKind.MODEL,),
        expected_audit_always_runs=(True,),
        expected_test_names=("orders_test",),
        expected_test_scope_deps=(
            (CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),),
        ),
        expected_test_expected_model_names=(("orders",),),
        expected_model_macro_deps=((),),
        expected_test_modes=("model",),
        expected_tested_macro_names=((),),
    ),
    AssembleCompiledProjectTestCase(
        description="assembles standalone audit always_run header option",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.toml": 'name = "demo"\nadapter = "duckdb"\n',
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS order_id\n",
            "audits/orders.sql": """
AUDIT (always_run: true);

SELECT order_id FROM __ref("orders") WHERE order_id IS NULL
""".strip()
            + "\n",
        },
        expected_model_names=("orders",),
        expected_model_deps=((),),
        expected_model_target_names=("orders",),
        expected_model_target_schemas=(None,),
        expected_source_names=(),
        expected_seed_names=(),
        expected_audit_names=("orders",),
        expected_audit_scope_deps=(
            (CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),),
        ),
        expected_audit_attached_target_kinds=(None,),
        expected_audit_always_runs=(True,),
        expected_test_names=(),
        expected_test_scope_deps=(),
        expected_test_expected_model_names=(),
        expected_model_macro_deps=((),),
        expected_test_modes=(),
        expected_tested_macro_names=(),
    ),
    AssembleCompiledProjectTestCase(
        description="assembles seed locations using local environment database templates",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.toml": """
name = "demo"
adapter = "duckdb"
default_target = "dev"

[vars]
project = "reporting"

[defaults]
schema = "analytics"

[targets]

[targets.dev]
database = "${ENV:TARGET_DB}_${project}"
schema = "seeds_${project}"
""".strip()
            + "\n",
            "sqlbuild_local.toml": """
[targets]

[targets.dev]
database = "${ENV:LOCAL_TARGET_DB}_${project}"
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
        expected_model_macro_deps=(),
        expected_test_modes=(),
        expected_tested_macro_names=(),
    ),
    AssembleCompiledProjectTestCase(
        description="assembles seed locations using seed declaration templates",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.toml": """
name = "demo"
adapter = "duckdb"
default_target = "dev"

[vars]
seed_schema_suffix = "lookups"

[defaults]
database = "default_db"
schema = "default_schema"

[targets]

[targets.dev]
database = "env_db"
schema = "env_schema"
""".strip()
            + "\n",
            "seeds/lookups.yml": """
seeds:
  - name: country_codes
    database: "${if(ENV:USE_SEED_DB, 'seed_db', CTX:destination.database)}"
    schema: "${CTX:destination.schema}_${seed_schema_suffix}"
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
        expected_seed_target_schemas=("env_schema_lookups",),
        expected_seed_target_databases=("seed_db",),
        expected_seed_target_qualified_names=(None,),
        expected_audit_names=(),
        expected_audit_scope_deps=(),
        expected_test_names=(),
        expected_test_scope_deps=(),
        expected_test_expected_model_names=(),
        expected_model_macro_deps=(),
        expected_test_modes=(),
        expected_tested_macro_names=(),
    ),
    AssembleCompiledProjectTestCase(
        description="assembles macro test scope from models using inferred macro deps",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.toml": 'name = "demo"\nadapter = "duckdb"\n',
            "macros/status.py": (
                'def normalize_status(value):\n    return f"LOWER(TRIM({value}))"\n'
            ),
            "models/orders.sql": (
                "MODEL ();\n\nSELECT @normalize_status(\"'  PAID  '\") AS status\n"
            ),
            "models/customers.sql": "MODEL ();\n\nSELECT 'active' AS status\n",
            "tests/unit/test_normalize_status.sql": """
TEST (mode: macro, name: "normalizes status");

WITH
input_values AS (SELECT '  PAID  ' AS raw_status),
__macro_actual__ AS (
  SELECT @normalize_status("raw_status") AS status FROM input_values
),
__macro_expected__ AS (SELECT 'paid' AS status)
SELECT 1
""".strip()
            + "\n",
        },
        expected_model_names=("customers", "orders"),
        expected_model_deps=((), ()),
        expected_model_target_names=("customers", "orders"),
        expected_model_target_schemas=(None, None),
        expected_source_names=(),
        expected_seed_names=(),
        expected_audit_names=(),
        expected_audit_scope_deps=(),
        expected_test_names=("normalizes status",),
        expected_test_scope_deps=(
            (CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),),
        ),
        expected_test_expected_model_names=((),),
        expected_model_macro_deps=((), ("normalize_status",)),
        expected_test_modes=("macro",),
        expected_tested_macro_names=(("normalize_status",),),
    ),
    AssembleCompiledProjectTestCase(
        description="applies environment namespace to managed source loader targets",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.toml": """
name = "demo"
adapter = "bigquery"
default_target = "dev"

[targets.dev]
database = "project_id"
schema = "analytics_dev"
""".strip()
            + "\n",
            "sources/raw.yml": """
sources:
  - name: raw_orders
    managed: true
    write_strategy: table
""".strip()
            + "\n",
            "loaders/raw_orders.py": """
from sqlbuild.loaders import loader

@loader
def raw_orders(ctx):
    return [{"id": 1}]
""".strip()
            + "\n",
        },
        expected_model_names=(),
        expected_model_deps=(),
        expected_model_target_names=(),
        expected_model_target_schemas=(),
        expected_source_names=("raw_orders",),
        expected_source_databases=("project_id",),
        expected_source_schemas=("analytics_dev",),
        expected_seed_names=(),
        expected_audit_names=(),
        expected_audit_scope_deps=(),
        expected_test_names=(),
        expected_test_scope_deps=(),
        expected_test_expected_model_names=(),
    ),
    AssembleCompiledProjectTestCase(
        description="assembles udf test scope from models using inferred udf deps",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.toml": 'name = "demo"\nadapter = "duckdb"\n',
            "functions/sql/format_cents.sql": """
FUNCTION (
  arguments (amount_cents INTEGER),
  returns VARCHAR,
);

'$' || CAST(amount_cents / 100 AS VARCHAR)
""".strip()
            + "\n",
            "models/orders.sql": ('MODEL ();\n\nSELECT __udf("format_cents")(1250) AS formatted\n'),
            "models/customers.sql": "MODEL ();\n\nSELECT 'active' AS status\n",
            "tests/unit/test_format_cents.sql": """
TEST (mode: udf, name: "formats cents");

WITH
input_values AS (SELECT 1250 AS amount_cents),
__udf_actual__ AS (
  SELECT __udf("format_cents")(amount_cents) AS formatted FROM input_values
),
__udf_expected__ AS (SELECT '$12.50' AS formatted)
SELECT 1
""".strip()
            + "\n",
        },
        expected_model_names=("customers", "orders"),
        expected_model_deps=(
            (),
            (CompiledObjectKey(resource_type=CompiledResourceType.UDF, name="format_cents"),),
        ),
        expected_model_target_names=("customers", "orders"),
        expected_model_target_schemas=(None, None),
        expected_source_names=(),
        expected_seed_names=(),
        expected_audit_names=(),
        expected_audit_scope_deps=(),
        expected_test_names=("formats cents",),
        expected_test_scope_deps=(
            (CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),),
        ),
        expected_test_expected_model_names=((),),
        expected_model_macro_deps=((), ()),
        expected_test_modes=("udf",),
        expected_tested_macro_names=(("format_cents",),),
    ),
    AssembleCompiledProjectTestCase(
        description="assembles table function test scope from inferred table function deps",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.toml": 'name = "demo"\nadapter = "duckdb"\n',
            "functions/sql/customer_orders.sql": """
FUNCTION (
  arguments (p_customer_id INTEGER),
  returns table (
    customer_id INTEGER,
    order_id INTEGER
  )
);

SELECT p_customer_id AS customer_id, 1 AS order_id
""".strip()
            + "\n",
            "tests/unit/test_customer_orders.sql": """
TEST (mode: table_fn, name: "returns customer orders");

WITH
__table_fn_actual__ AS (
  SELECT customer_id, order_id FROM __table_fn("customer_orders")(42)
),
__table_fn_expected__ AS (SELECT 42 AS customer_id, 1 AS order_id)
SELECT 1
""".strip()
            + "\n",
        },
        expected_model_names=(),
        expected_model_deps=(),
        expected_model_target_names=(),
        expected_model_target_schemas=(),
        expected_source_names=(),
        expected_seed_names=(),
        expected_audit_names=(),
        expected_audit_scope_deps=(),
        expected_test_names=("returns customer orders",),
        expected_test_scope_deps=(
            (
                CompiledObjectKey(
                    resource_type=CompiledResourceType.TABLE_FN, name="customer_orders"
                ),
            ),
        ),
        expected_test_expected_model_names=((),),
        expected_model_macro_deps=(),
        expected_test_modes=("table_fn",),
        expected_tested_macro_names=(("customer_orders",),),
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
    monkeypatch.setenv("USE_SEED_DB", "1")
    write_repo_files(tmp_path, test_case.repo_files)
    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    compile_inputs: CompileProjectInputs = build_compile_inputs(discovered, run_id="test_run_id")
    compiled: CompiledProject = assemble_compiled_project(compile_inputs)

    assert tuple(m.name for m in compiled.models) == test_case.expected_model_names
    assert tuple(m.deps for m in compiled.models) == test_case.expected_model_deps
    assert tuple(m.macro_deps for m in compiled.models) == test_case.expected_model_macro_deps
    assert (
        tuple(m.destination.name for m in compiled.models) == test_case.expected_model_target_names
    )
    assert (
        tuple(m.destination.schema for m in compiled.models)
        == test_case.expected_model_target_schemas
    )
    assert tuple(s.name for s in compiled.sources) == test_case.expected_source_names
    assert (
        tuple(s.source_entry.database for s in compiled.sources)
        == test_case.expected_source_databases
    )
    assert (
        tuple(s.source_entry.schema for s in compiled.sources) == test_case.expected_source_schemas
    )
    assert tuple(s.name for s in compiled.seeds) == test_case.expected_seed_names
    assert (
        tuple(s.destination.schema for s in compiled.seeds)
        == test_case.expected_seed_target_schemas
    )
    assert (
        tuple(s.destination.database for s in compiled.seeds)
        == test_case.expected_seed_target_databases
    )
    assert (
        tuple(s.destination.qualified_name for s in compiled.seeds)
        == test_case.expected_seed_target_qualified_names
    )
    assert tuple(a.name for a in compiled.audits) == test_case.expected_audit_names
    assert tuple(a.scope_deps for a in compiled.audits) == test_case.expected_audit_scope_deps
    assert (
        tuple(a.attached_target_kind for a in compiled.audits)
        == test_case.expected_audit_attached_target_kinds
    )
    assert tuple(a.always_run for a in compiled.audits) == test_case.expected_audit_always_runs
    assert tuple(t.name for t in compiled.sql_tests) == test_case.expected_test_names
    assert tuple(t.scope_deps for t in compiled.sql_tests) == test_case.expected_test_scope_deps
    assert tuple(t.mode.value for t in compiled.sql_tests) == test_case.expected_test_modes
    assert (
        tuple(compiled_sql_test_tested_resource_names(t) for t in compiled.sql_tests)
        == test_case.expected_tested_macro_names
    )
    assert (
        tuple(compiled_sql_test_expected_model_names(t) for t in compiled.sql_tests)
        == test_case.expected_test_expected_model_names
    )
