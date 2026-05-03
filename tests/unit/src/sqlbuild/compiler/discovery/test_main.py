from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.main import discover_project_inputs
from tests.unit.src.sqlbuild.compiler.discovery._test_helpers import (
    base_repo_files,
    write_repo_files,
)
from tests.unit.src.sqlbuild.compiler.discovery._test_types import (
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
                "sources/raw.yml": "sources: []\n",
                "seeds/country_codes.csv": "country_code,country_name\nUS,United States\n",
                "seeds/schema.yml": "seeds: []\n",
                "tests/unit/orders.sql": "TEST ();\nSELECT 1\n",
                "audits/generic/not_null.sql": "AUDIT ();\nSELECT 1\n",
                "macros/name_helpers.py": "def slug() -> str:\n    return 'slug'\n",
                "target/manifest.json": '{"metadata": {"dbt_schema_version": "v12"}}\n',
                "adapter.py": "class ExampleAdapter:\n    pass\n",
                "sqlbuild_local.yml": "environment: dev\n",
            },
            expected_model_paths=("models/staging/orders.sql",),
            expected_model_header_values=({},),
            expected_model_query_sql=("select 1",),
            expected_schema_paths=("models/staging/schema.yml", "seeds/schema.yml"),
            expected_source_paths=("sources/raw.yml",),
            expected_seed_paths=("seeds/country_codes.csv",),
            expected_test_paths=("tests/unit/orders.sql",),
            expected_test_block_indexes=(1,),
            expected_test_block_names=(None,),
            expected_test_block_sql_bodies=("SELECT 1",),
            expected_audit_paths=("audits/generic/not_null.sql",),
            expected_macro_paths=("macros/name_helpers.py",),
            expected_manifest_path="target/manifest.json",
            expected_adapter_path="adapter.py",
        )
    ],
    ids=["discovers raw project inputs across authored project surfaces"],
)
def test_given_project_repo_slice_when_discovering_inputs_then_it_returns_expected_raw_inventory(
    test_case: DiscoverProjectInputsTestCase,
    tmp_path: Path,
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
        tuple(str(source_file.relative_path) for source_file in discovered_inputs.source_files)
        == test_case.expected_source_paths
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
        tuple(str(audit_file.relative_path) for audit_file in discovered_inputs.audit_files)
        == test_case.expected_audit_paths
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
