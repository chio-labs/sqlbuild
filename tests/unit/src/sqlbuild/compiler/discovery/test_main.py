from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from tests.unit.src.sqlbuild.compiler.discovery._test_helpers import (
    base_repo_files,
)
from tests.unit.src.sqlbuild.compiler.discovery._test_types import (
    DiscoverProjectInputsErrorTestCase,
    DiscoverProjectInputsTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DiscoverProjectInputsTestCase(
            description="discovers raw project inputs across authored project surfaces",
            repo_files=base_repo_files()
            | {
                "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
                "models/staging/schema.yml": "models: []\n",
                "sources/raw.yml": """
sources:
  - name: raw_orders
    schema: public
    table: orders
""".strip()
                + "\n",
                "seeds/country_codes.csv": "country_code,country_name\nUS,United States\n",
                "seeds/lookups.yml": """
seeds:
  - name: country_codes
    columns:
      - name: country_code
        type: VARCHAR
      - name: country_name
        type: VARCHAR
""".strip()
                + "\n",
                "tests/unit/orders.sql": "TEST ();\nSELECT 1\n",
                "tests/legacy_orders.sql": "TEST ();\nSELECT 2\n",
                "tests/scenarios/revenue/revenue__customer_refund.sql": """
SCENARIO (description: "Customer refund", tags: ["revenue"]);

WITH
__expected__daily_revenue AS (
  SELECT 1 AS order_id
)
SELECT 1
""",
                "audits/generic/not_null.sql": "AUDIT ();\nSELECT 1\n",
                "macros/name_helpers.py": "def slug() -> str:\n    return 'slug'\n",
                "loaders/raw_orders.py": """
from sqlbuild.loaders import loader

@loader
def fetch_orders(ctx):
    return []
""",
                "tasks/windows.py": """
from sqlbuild.tasks import task

@task(tags=("api",), group="ingestion")
def fetch_window(ctx):
    return {"window": "today"}
""",
                "assets/exports.py": """
from sqlbuild.assets import asset

@asset(columns=[{"name": "customer_id", "type": "string"}])
def export_customers(ctx):
    return {"uri": "s3://exports/customers.parquet"}
""",
                "checks/exports.py": """
from sqlbuild.checks import check
from assets.exports import export_customers

@check(depends_on=export_customers, severity="warn")
def export_customers_exists(ctx):
    return True
""",
                "target/manifest.json": '{"metadata": {"dbt_schema_version": "v12"}}\n',
                "adapter.py": "class ExampleAdapter:\n    pass\n",
                "sqlbuild_local.toml": 'environment = "dev"\n',
            },
            expected_model_paths=("models/staging/orders.sql",),
            expected_model_header_values=({},),
            expected_model_query_sql=("select 1",),
            expected_schema_paths=("models/staging/schema.yml", "seeds/lookups.yml"),
            expected_schema_model_names=((), ()),
            expected_schema_seed_names=((), ("country_codes",)),
            expected_source_paths=("sources/raw.yml",),
            expected_source_entry_names=(("raw_orders",),),
            expected_seed_paths=("seeds/country_codes.csv",),
            expected_test_paths=("tests/unit/orders.sql",),
            expected_test_block_indexes=(1,),
            expected_test_block_names=(None,),
            expected_test_block_sql_bodies=("SELECT 1",),
            expected_scenario_paths=("tests/scenarios/revenue/revenue__customer_refund.sql",),
            expected_scenario_names=("revenue__customer_refund",),
            expected_scenario_header_values=(
                {"description": "Customer refund", "tags": ["revenue"]},
            ),
            expected_scenario_sql_bodies=(
                "WITH\n__expected__daily_revenue AS (\n  SELECT 1 AS order_id\n)\nSELECT 1",
            ),
            expected_audit_paths=("audits/generic/not_null.sql",),
            expected_audit_block_indexes=(1,),
            expected_audit_block_names=(None,),
            expected_audit_block_sql_bodies=("SELECT 1",),
            expected_macro_paths=("macros/name_helpers.py",),
            expected_loader_names=("fetch_orders",),
            expected_adapter_path="adapter.py",
            expected_task_names=("fetch_window",),
            expected_asset_names=("export_customers",),
            expected_check_names=("export_customers_exists",),
        )
    ],
    ids=["discovers raw project inputs across authored project surfaces"],
)
def test_given_project_repo_slice_when_discovering_inputs_then_it_returns_expected_raw_inventory(
    test_case: DiscoverProjectInputsTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    discovered_inputs: object = discover_project_inputs(project_dir=tmp_path)

    assert (
        tuple(str(model_file.relative_path) for model_file in discovered_inputs.model_files)
        == test_case.expected_model_paths
    )
    assert (
        tuple(model_file.header_values for model_file in discovered_inputs.model_files)
        == test_case.expected_model_header_values
    )
    assert (
        tuple(model_file.query_sql for model_file in discovered_inputs.model_files)
        == test_case.expected_model_query_sql
    )
    assert (
        tuple(str(schema_file.relative_path) for schema_file in discovered_inputs.schema_files)
        == test_case.expected_schema_paths
    )
    assert (
        tuple(
            tuple(model_entry.name for model_entry in schema_file.model_entries)
            for schema_file in discovered_inputs.schema_files
        )
        == test_case.expected_schema_model_names
    )
    assert (
        tuple(
            tuple(seed_entry.name for seed_entry in schema_file.seed_entries)
            for schema_file in discovered_inputs.schema_files
        )
        == test_case.expected_schema_seed_names
    )
    assert (
        tuple(str(source_file.relative_path) for source_file in discovered_inputs.source_files)
        == test_case.expected_source_paths
    )
    assert (
        tuple(
            tuple(source_entry.name for source_entry in source_file.source_entries)
            for source_file in discovered_inputs.source_files
        )
        == test_case.expected_source_entry_names
    )
    assert (
        tuple(str(seed_file.relative_path) for seed_file in discovered_inputs.seed_files)
        == test_case.expected_seed_paths
    )
    assert (
        tuple(str(test_file.relative_path) for test_file in discovered_inputs.test_files)
        == test_case.expected_test_paths
    )
    assert (
        tuple(block.test_index for block in discovered_inputs.test_files[0].blocks)
        == test_case.expected_test_block_indexes
    )
    assert (
        tuple(block.name for block in discovered_inputs.test_files[0].blocks)
        == test_case.expected_test_block_names
    )
    assert (
        tuple(block.sql_body for block in discovered_inputs.test_files[0].blocks)
        == test_case.expected_test_block_sql_bodies
    )
    assert (
        tuple(
            str(scenario_file.relative_path) for scenario_file in discovered_inputs.scenario_files
        )
        == test_case.expected_scenario_paths
    )
    assert (
        tuple(scenario_file.name for scenario_file in discovered_inputs.scenario_files)
        == test_case.expected_scenario_names
    )
    assert (
        tuple(scenario_file.header_values for scenario_file in discovered_inputs.scenario_files)
        == test_case.expected_scenario_header_values
    )
    assert (
        tuple(scenario_file.sql_body for scenario_file in discovered_inputs.scenario_files)
        == test_case.expected_scenario_sql_bodies
    )
    assert (
        tuple(str(audit_file.relative_path) for audit_file in discovered_inputs.audit_files)
        == test_case.expected_audit_paths
    )
    assert (
        tuple(block.audit_index for block in discovered_inputs.audit_files[0].blocks)
        == test_case.expected_audit_block_indexes
    )
    assert (
        tuple(block.name for block in discovered_inputs.audit_files[0].blocks)
        == test_case.expected_audit_block_names
    )
    assert (
        tuple(block.sql_body for block in discovered_inputs.audit_files[0].blocks)
        == test_case.expected_audit_block_sql_bodies
    )
    assert (
        tuple(str(macro_file.relative_path) for macro_file in discovered_inputs.macro_files)
        == test_case.expected_macro_paths
    )
    assert (
        tuple(loader_function.name for loader_function in discovered_inputs.loader_functions)
        == test_case.expected_loader_names
    )
    assert (
        tuple(task_function.name for task_function in discovered_inputs.task_functions)
        == test_case.expected_task_names
    )
    assert (
        tuple(asset_function.name for asset_function in discovered_inputs.asset_functions)
        == test_case.expected_asset_names
    )
    assert (
        tuple(check_function.name for check_function in discovered_inputs.check_functions)
        == test_case.expected_check_names
    )
    assert (
        None
        if discovered_inputs.adapter_file is None
        else str(discovered_inputs.adapter_file.relative_path)
    ) == test_case.expected_adapter_path
    assert discovered_inputs.project_config.name == "demo"
    assert discovered_inputs.project_config.adapter == "duckdb"
    assert discovered_inputs.local_config.environment == "dev"


DISCOVERY_ERROR_TEST_CASES: list[DiscoverProjectInputsErrorTestCase] = [
    DiscoverProjectInputsErrorTestCase(
        description="raises on duplicate source names across files",
        repo_files=base_repo_files()
        | {
            "sources/raw_orders.yml": """
sources:
  - name: raw_orders
    schema: public
    table: orders
""".strip()
            + "\n",
            "sources/raw_orders_duplicate.yml": """
sources:
  - name: raw_orders
    schema: public
    table: orders_backup
""".strip()
            + "\n",
        },
        expected_error_fragment="Duplicate source declaration found for 'raw_orders'",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises on schema yml model metadata",
        repo_files=base_repo_files()
        | {
            "models/staging/schema.yml": """
models:
  - name: stg_orders
""".strip()
            + "\n",
        },
        expected_error_fragment="model metadata must live in the model file MODEL",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises on duplicate schema seed names across files",
        repo_files=base_repo_files()
        | {
            "seeds/a.yml": """
seeds:
  - name: country_codes
    columns:
      - name: country_code
        type: VARCHAR
""".strip()
            + "\n",
            "seeds/b.yml": """
seeds:
  - name: country_codes
    columns:
      - name: country_code
        type: VARCHAR
""".strip()
            + "\n",
        },
        expected_error_fragment="Duplicate seed declaration found for 'country_codes'",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises on duplicate model file names across directories",
        repo_files=base_repo_files()
        | {
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
            "models/marts/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        expected_error_fragment="Duplicate model file name found for 'orders'",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises on duplicate scenario file names across directories",
        repo_files=base_repo_files()
        | {
            "tests/scenarios/revenue/customer_refund.sql": "SCENARIO ();\nSELECT 1\n",
            "tests/scenarios/support/customer_refund.sql": "SCENARIO ();\nSELECT 1\n",
        },
        expected_error_fragment="Duplicate scenario file name found for 'customer_refund'",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when model and source names collide",
        repo_files=base_repo_files()
        | {
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
            "sources/raw.yml": """
sources:
  - name: orders
    table: orders
""".strip()
            + "\n",
        },
        expected_error_fragment="Logical relation name 'orders' is declared as both model",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when source and seed names collide",
        repo_files=base_repo_files()
        | {
            "sources/raw.yml": """
sources:
  - name: country_codes
    table: country_codes
""".strip()
            + "\n",
            "seeds/schema.yml": """
seeds:
  - name: country_codes
    columns:
      - name: country_code
        type: VARCHAR
""".strip()
            + "\n",
        },
        expected_error_fragment="Logical relation name 'country_codes' is declared as both source",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when a source references an unknown loader",
        repo_files=base_repo_files()
        | {
            "sources/raw.yml": """
sources:
  - name: raw_orders
    managed: true
""".strip()
            + "\n",
        },
        expected_error_fragment="Managed source 'raw_orders' in sources/raw.yml requires loader",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when loader names are duplicated",
        repo_files=base_repo_files()
        | {
            "loaders/a.py": """
from sqlbuild.loaders import loader

@loader
def raw_orders(ctx):
    return []
""",
            "loaders/b.py": """
from sqlbuild.loaders import loader

@loader
def raw_orders(ctx):
    return []
""",
        },
        expected_error_fragment="Duplicate source loader found for 'raw_orders'",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when unmanaged source name collides with loader name",
        repo_files=base_repo_files()
        | {
            "sources/raw.yml": """
sources:
  - name: fetch_orders
    table: fetch_orders
""".strip()
            + "\n",
            "loaders/raw_orders.py": """
from sqlbuild.loaders import loader

@loader
def fetch_orders(ctx):
    return []
""",
        },
        expected_error_fragment="Source 'fetch_orders' in sources/raw.yml conflicts with loader",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when unmanaged source name collides with terminal loader name",
        repo_files=base_repo_files()
        | {
            "sources/raw.yml": """
sources:
  - name: raw_orders
    table: raw_orders
""".strip()
            + "\n",
            "loaders/raw_orders.py": """
from sqlbuild.loaders import loader

@loader
def raw_orders(ctx):
    return []
""",
        },
        expected_error_fragment="Source 'raw_orders' in sources/raw.yml conflicts with loader",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when loader dependency is not decorated",
        repo_files=base_repo_files()
        | {
            "loaders/events.py": """
from sqlbuild.loaders import loader

def fetch_events(ctx):
    return []

@loader(depends_on=[fetch_events])
def enriched_events(ctx):
    return []
""",
        },
        expected_error_fragment="Loader 'enriched_events' depends on an unknown loader",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when loader dependencies contain a cycle",
        repo_files=base_repo_files()
        | {
            "loaders/events.py": """
from sqlbuild.loaders import loader

def fetch_events(ctx):
    return []

@loader(depends_on=[fetch_events])
def enriched_events(ctx):
    return []

fetch_events = loader(depends_on=[enriched_events])(fetch_events)
""",
        },
        expected_error_fragment="Loader dependency cycle detected",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when terminal loader owns source config",
        repo_files=base_repo_files()
        | {
            "sources/raw.yml": """
sources:
  - name: raw_orders
    managed: true
    write_strategy: table
""".strip()
            + "\n",
            "loaders/raw_orders.py": """
from sqlbuild.loaders import loader

@loader(write_strategy="table", columns=[{"name": "id", "type": "INTEGER"}])
def raw_orders(ctx):
    return []
""",
        },
        expected_error_fragment="terminal source loader write and schema config must be declared",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when task and asset names are duplicated",
        repo_files=base_repo_files()
        | {
            "tasks/export_customers.py": """
from sqlbuild.tasks import task

@task
def export_customers(ctx):
    return None
""",
            "assets/export_customers.py": """
from sqlbuild.assets import asset

@asset
def export_customers(ctx):
    return None
""",
        },
        expected_error_fragment="Duplicate Python node found for 'export_customers'",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when check name collides with task name",
        repo_files=base_repo_files()
        | {
            "tasks/export_customers.py": """
from sqlbuild.tasks import task

@task
def export_customers(ctx):
    return None
""",
            "checks/export_customers.py": """
from sqlbuild.checks import check
from tasks.export_customers import export_customers

@check(depends_on=export_customers, name="export_customers")
def export_customers_check(ctx):
    return True
""",
        },
        expected_error_fragment="Duplicate Python node found for 'export_customers'",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when model name collides with task name",
        repo_files=base_repo_files()
        | {
            "models/marts/export_customers.sql": "MODEL ();\n\nselect 1\n",
            "tasks/export_customers.py": """
from sqlbuild.tasks import task

@task
def export_customers(ctx):
    return None
""",
        },
        expected_error_fragment=(
            "Selectable resource name 'export_customers' is declared as both model"
        ),
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when seed name collides with asset name",
        repo_files=base_repo_files()
        | {
            "seeds/schema.yml": """
seeds:
  - name: export_customers
    columns:
      - name: customer_id
        type: INTEGER
""".strip()
            + "\n",
            "seeds/export_customers.csv": "customer_id\n1\n",
            "assets/export_customers.py": """
from sqlbuild.assets import asset

@asset
def export_customers(ctx):
    return None
""",
        },
        expected_error_fragment=(
            "Selectable resource name 'export_customers' is declared as both seed"
        ),
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when source name collides with check name",
        repo_files=base_repo_files()
        | {
            "sources/raw.yml": """
sources:
  - name: export_customers_exists
    table: export_customers_exists
""".strip()
            + "\n",
            "tasks/export_customers.py": """
from sqlbuild.tasks import task

@task
def export_customers(ctx):
    return None
""",
            "checks/export_customers.py": """
from sqlbuild.checks import check
from tasks.export_customers import export_customers

@check(depends_on=export_customers)
def export_customers_exists(ctx):
    return True
""",
        },
        expected_error_fragment=(
            "Selectable resource name 'export_customers_exists' is declared as both source"
        ),
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when sql function name collides with python function name",
        repo_files=base_repo_files()
        | {
            "functions/sql/is_large_order.sql": """
FUNCTION (
  arguments (amount INTEGER),
  returns BOOLEAN,
);

amount > 100
""".strip()
            + "\n",
            "functions/python/is_large_order.py": """
from sqlbuild.functions import udf

@udf(arguments={"amount": "INTEGER"}, returns="BOOLEAN", runtime_version="3.11")
def main(amount):
    return amount > 100
""".strip()
            + "\n",
        },
        expected_error_fragment=(
            "Selectable resource name 'is_large_order' is declared as both function"
        ),
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when function name collides with loader name",
        repo_files=base_repo_files()
        | {
            "functions/sql/fetch_orders.sql": """
FUNCTION (
  arguments (amount INTEGER),
  returns BOOLEAN,
);

amount > 100
""".strip()
            + "\n",
            "loaders/fetch_orders.py": """
from sqlbuild.loaders import loader

@loader
def fetch_orders(ctx):
    return []
""",
        },
        expected_error_fragment=(
            "Selectable resource name 'fetch_orders' is declared as both function"
        ),
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when task dependency is not decorated",
        repo_files=base_repo_files()
        | {
            "tasks/windows.py": """
from sqlbuild.tasks import task

def fetch_window(ctx):
    return None

@task(depends_on=fetch_window)
def export_window(ctx):
    return None
""",
        },
        expected_error_fragment="Python node 'export_window' depends on an unknown Python node",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when task and asset dependencies contain a cycle",
        repo_files=base_repo_files()
        | {
            "tasks/windows.py": """
from sqlbuild.tasks import task

def fetch_window(ctx):
    return None

@task(depends_on=fetch_window)
def enrich_window(ctx):
    return None

fetch_window = task(depends_on=enrich_window)(fetch_window)
""",
        },
        expected_error_fragment="Python node dependency cycle detected",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when check dependency is not decorated",
        repo_files=base_repo_files()
        | {
            "checks/exports.py": """
from sqlbuild.checks import check

def export_customers(ctx):
    return None

@check(depends_on=export_customers)
def export_customers_exists(ctx):
    return True
""",
        },
        expected_error_fragment="Check 'export_customers_exists' depends on an unknown Python node",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when loader declares SQL model dependency",
        repo_files=base_repo_files()
        | {
            "loaders/orders.py": """
from sqlbuild.loaders import loader
from sqlbuild.refs import model

@loader(depends_on=[model('stg_orders')])
def load_orders(ctx):
    return []
""",
        },
        expected_error_fragment="Loader 'load_orders' depends on SQL resource 'stg_orders'",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when check declares SQL model dependency",
        repo_files=base_repo_files()
        | {
            "checks/orders.py": """
from sqlbuild.checks import check
from sqlbuild.refs import model

@check(depends_on=model('stg_orders'))
def check_orders(ctx):
    return True
""",
        },
        expected_error_fragment="Check 'check_orders' depends on SQL resource 'stg_orders'",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when check depends on check",
        repo_files=base_repo_files()
        | {
            "assets/exports.py": """
from sqlbuild.assets import asset

@asset
def export_customers(ctx):
    return None
""",
            "checks/exports.py": """
from sqlbuild.checks import check
from assets.exports import export_customers

@check(depends_on=export_customers)
def export_customers_exists(ctx):
    return True

@check(depends_on=export_customers_exists)
def export_customers_recent(ctx):
    return True
""",
        },
        expected_error_fragment="Check 'export_customers_recent' depends on another check",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when seeds are declared outside seeds directory",
        repo_files=base_repo_files()
        | {
            "models/schema.yml": """
seeds:
  - name: country_codes
    columns:
      - name: country_code
        type: VARCHAR
""".strip()
            + "\n",
        },
        expected_error_fragment="seed declarations must live under seeds/",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when a seed declaration uses yaml extension",
        repo_files=base_repo_files()
        | {
            "seeds/lookups.yaml": "seeds: []\n",
        },
        expected_error_fragment=r"\.yaml is not supported",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when seed csv basenames are duplicated",
        repo_files=base_repo_files()
        | {
            "seeds/a/country_codes.csv": "country_code\nUS\n",
            "seeds/b/country_codes.csv": "country_code\nCA\n",
            "seeds/lookups.yml": """
seeds:
  - name: country_codes
    columns:
      - name: country_code
        type: VARCHAR
""".strip()
            + "\n",
        },
        expected_error_fragment="Duplicate seed CSV name 'country_codes' found",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when a declared seed has no matching csv file",
        repo_files=base_repo_files()
        | {
            "seeds/schema.yml": """
seeds:
  - name: country_codes
    columns:
      - name: country_code
        type: VARCHAR
""".strip()
            + "\n",
        },
        expected_error_fragment="has no matching CSV file under seeds/",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when a seed csv has no matching declaration",
        repo_files=base_repo_files()
        | {
            "seeds/country_codes.csv": "country_code\nUS\n",
        },
        expected_error_fragment="has no matching declaration for seed 'country_codes'",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when a seed csv header does not match declared columns",
        repo_files=base_repo_files()
        | {
            "seeds/schema.yml": """
seeds:
  - name: country_codes
    columns:
      - name: country_code
        type: VARCHAR
      - name: country_name
        type: VARCHAR
""".strip()
            + "\n",
            "seeds/country_codes.csv": "country_name,country_code\nUS,United States\n",
        },
        expected_error_fragment="does not match declared seed columns",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when a seed csv has duplicate header columns",
        repo_files=base_repo_files()
        | {
            "seeds/schema.yml": """
seeds:
  - name: country_codes
    columns:
      - name: country_code
        type: VARCHAR
      - name: country_name
        type: VARCHAR
""".strip()
            + "\n",
            "seeds/country_codes.csv": "country_code,country_code\nUS,United States\n",
        },
        expected_error_fragment="contains duplicate CSV header column 'country_code'",
    ),
    DiscoverProjectInputsErrorTestCase(
        description="raises when path defaults match no model paths",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.toml": """
name = "demo"
adapter = "duckdb"

[path_defaults.stagingg]
schema = "staging"
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        expected_error_fragment=r"path_defaults\['stagingg'\] does not match any model paths",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    DISCOVERY_ERROR_TEST_CASES,
    ids=[case.description for case in DISCOVERY_ERROR_TEST_CASES],
)
def test_given_discovery_conflicts_when_discovering_inputs_then_it_raises_clear_errors(
    test_case: DiscoverProjectInputsErrorTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        discover_project_inputs(project_dir=tmp_path)
