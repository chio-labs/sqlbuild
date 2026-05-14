from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from tests.unit.src.sqlbuild.compiler.discovery._test_helpers import (
    base_repo_files,
)
from tests.unit.src.sqlbuild.compiler.discovery._test_types import (
    DiscoverDbtManifestTargetPathTestCase,
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
            expected_manifest_path=None,
            expected_adapter_path="adapter.py",
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
        None
        if discovered_inputs.dbt_manifest_file is None
        else str(discovered_inputs.dbt_manifest_file.relative_path)
    ) == test_case.expected_manifest_path
    assert (
        None
        if discovered_inputs.adapter_file is None
        else str(discovered_inputs.adapter_file.relative_path)
    ) == test_case.expected_adapter_path
    assert discovered_inputs.project_config.name == "demo"
    assert discovered_inputs.project_config.adapter == "duckdb"
    assert discovered_inputs.local_config.environment == "dev"


@pytest.mark.parametrize(
    "test_case",
    [
        DiscoverDbtManifestTargetPathTestCase(
            description="discovers dbt manifest from configured target path outside project",
            repo_files=base_repo_files()
            | {
                "sqlbuild_project.toml": """
name = "demo"
adapter = "duckdb"

[dbt]
target_path = "../dbt_project/target"
""".strip()
                + "\n",
                "../dbt_project/target/manifest.json": (
                    '{"metadata": {"dbt_schema_version": "v12"}}\n'
                ),
            },
            expected_manifest_path="../dbt_project/target/manifest.json",
        )
    ],
    ids=["discovers dbt manifest from configured target path outside project"],
)
def test_given_dbt_target_path_when_discovering_inputs_then_loads_configured_manifest(
    test_case: DiscoverDbtManifestTargetPathTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        test_case.repo_files,
    )

    discovered_inputs: object = discover_project_inputs(project_dir=tmp_path)

    assert discovered_inputs.dbt_manifest_file is not None
    assert (
        str(discovered_inputs.dbt_manifest_file.relative_path) == test_case.expected_manifest_path
    )


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
