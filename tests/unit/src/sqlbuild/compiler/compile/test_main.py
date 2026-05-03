from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.compile.main import build_compile_inputs
from sqlbuild.compiler.compile.models import CompileProjectInputs
from sqlbuild.compiler.discovery.main import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from tests.unit.src.sqlbuild.compiler.compile._test_helpers import (
    base_repo_files,
    write_repo_files,
)
from tests.unit.src.sqlbuild.compiler.compile._test_types import (
    BuildCompileInputsErrorTestCase,
    BuildCompileInputsTestCase,
)

TEST_CASES: list[BuildCompileInputsTestCase] = [
    BuildCompileInputsTestCase(
        description="attaches schema metadata to matching models and seeds and normalizes sources",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb

defaults:
  materialized: table
  schema: analytics
  batch_size: 1h

path_defaults:
  models/staging:
    materialized: view
    schema: staging
  models/staging/nested:
    schema: nested
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
            "models/staging/nested/orders_enriched.sql": """
MODEL (
  materialized: incremental,
  batch_size: 30m,
);

select 1
""".strip()
            + "\n",
            "models/staging/schema.yml": """
models:
  - name: orders
    columns:
      - name: order_id
        type: VARCHAR
""".strip()
            + "\n",
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
            "seeds/country_codes.csv": "country_code,country_name\nUS,United States\n",
            "sources/raw.yml": """
sources:
  - name: raw_orders
    schema: public
    table: orders
""".strip()
            + "\n",
        },
        expected_model_schema_names=(None, "orders"),
        expected_model_config_values=(
            {"materialized": "incremental", "schema": "nested", "batch_size": "30m"},
            {"materialized": "view", "schema": "staging", "batch_size": "1h"},
        ),
        expected_model_path_defaults=("models/staging/nested", "models/staging"),
        expected_seed_names=("country_codes",),
        expected_source_names=("raw_orders",),
    ),
    BuildCompileInputsTestCase(
        description="allows models with no matching schema metadata",
        repo_files=base_repo_files() | {"models/staging/orders.sql": "MODEL ();\n\nselect 1\n"},
        expected_model_schema_names=(None,),
        expected_model_config_values=({},),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=(),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_discovered_inputs_when_building_compile_inputs_then_it_attaches_metadata(
    test_case: BuildCompileInputsTestCase,
    tmp_path: Path,
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    compile_inputs: CompileProjectInputs = build_compile_inputs(discovered_inputs)

    assert (
        tuple(
            None if model_input.schema_entry is None else model_input.schema_entry.name
            for model_input in compile_inputs.model_inputs
        )
        == test_case.expected_model_schema_names
    )
    assert (
        tuple(model_input.config.values for model_input in compile_inputs.model_inputs)
        == test_case.expected_model_config_values
    )
    assert (
        tuple(
            model_input.config.matched_path_default for model_input in compile_inputs.model_inputs
        )
        == test_case.expected_model_path_defaults
    )
    assert (
        tuple(seed_input.schema_entry.name for seed_input in compile_inputs.seed_inputs)
        == test_case.expected_seed_names
    )
    assert (
        tuple(source_input.source_entry.name for source_input in compile_inputs.source_inputs)
        == test_case.expected_source_names
    )


COMPILE_ERROR_TEST_CASES: list[BuildCompileInputsErrorTestCase] = [
    BuildCompileInputsErrorTestCase(
        description=(
            "raises when a schema model declaration is outside its effective directory scope"
        ),
        repo_files=base_repo_files()
        | {
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
            "models/marts/schema.yml": """
models:
  - name: orders
""".strip()
            + "\n",
        },
        expected_error_fragment="does not match any discovered model file in that directory scope",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when a seed csv exists without a matching schema declaration",
        repo_files=base_repo_files()
        | {
            "seeds/extra_seed.csv": "country_code\nUS\n",
        },
        expected_error_fragment="has no matching seed declaration in schema.yml",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    COMPILE_ERROR_TEST_CASES,
    ids=[case.description for case in COMPILE_ERROR_TEST_CASES],
)
def test_given_attachment_conflicts_when_building_compile_inputs_then_it_raises_clear_errors(
    test_case: BuildCompileInputsErrorTestCase,
    tmp_path: Path,
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        build_compile_inputs(discovered_inputs)
