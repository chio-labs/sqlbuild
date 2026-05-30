from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.helpers.diff import (
    compile_project_for_diff_environment,
    resolve_diff_model_names,
)
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import (
    DiffSelectorIntegrationTestCase,
)

_PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "demo"\nadapter = "duckdb"\ndefault_environment = "dev"\n\n'
        '[connection]\ndatabase = ":memory:"\n\n'
        '[environments.dev]\nschema = "dev_schema"\n'
    ),
    "models/staging/stg_orders.sql": (
        "MODEL (materialized table\ntags [staging]);\n\nSELECT 1 AS order_id"
    ),
    "models/staging/stg_customers.sql": (
        "MODEL (materialized table\ntags [staging]);\n\nSELECT 1 AS customer_id"
    ),
    "models/intermediate/int_orders.sql": (
        'MODEL (materialized table\ntags [core]);\n\nSELECT order_id FROM __ref("stg_orders")'
    ),
    "models/marts/fact_orders.sql": (
        'MODEL (materialized table\ntags [core, mart]);\n\nSELECT order_id FROM __ref("int_orders")'
    ),
    "models/marts/dim_customers.sql": (
        'MODEL (materialized table\ntags [mart]);\n\nSELECT customer_id FROM __ref("stg_customers")'
    ),
}

TEST_CASES: list[DiffSelectorIntegrationTestCase] = [
    DiffSelectorIntegrationTestCase(
        description="name selector returns a single model",
        select=("fact_orders",),
        exclude=(),
        expected_model_names=frozenset(("fact_orders",)),
    ),
    DiffSelectorIntegrationTestCase(
        description="path selector returns models under folder",
        select=("path:models/staging",),
        exclude=(),
        expected_model_names=frozenset(("stg_orders", "stg_customers")),
    ),
    DiffSelectorIntegrationTestCase(
        description="Windows-style path selector returns models under folder",
        select=("path:models\\staging",),
        exclude=(),
        expected_model_names=frozenset(("stg_orders", "stg_customers")),
    ),
    DiffSelectorIntegrationTestCase(
        description="tag selector returns tagged models",
        select=("tag:mart",),
        exclude=(),
        expected_model_names=frozenset(("fact_orders", "dim_customers")),
    ),
    DiffSelectorIntegrationTestCase(
        description="upstream expansion includes model ancestors",
        select=("+fact_orders",),
        exclude=(),
        expected_model_names=frozenset(("stg_orders", "int_orders", "fact_orders")),
    ),
    DiffSelectorIntegrationTestCase(
        description="downstream expansion includes model descendants",
        select=("stg_orders+",),
        exclude=(),
        expected_model_names=frozenset(("stg_orders", "int_orders", "fact_orders")),
    ),
    DiffSelectorIntegrationTestCase(
        description="exclude subtracts from selected models",
        select=("tag:mart",),
        exclude=("dim_customers",),
        expected_model_names=frozenset(("fact_orders",)),
    ),
    DiffSelectorIntegrationTestCase(
        description="comma selector intersects resolved sets",
        select=("tag:core,path:models/marts",),
        exclude=(),
        expected_model_names=frozenset(("fact_orders",)),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_compiled_project_when_resolving_diff_selectors_then_returns_expected_models(
    test_case: DiffSelectorIntegrationTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, _PROJECT_FILES)
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    project: CompiledProject = compile_project_for_diff_environment(
        discovered_inputs=discovered_inputs,
        adapter=DuckDbAdapter(),
        environment_name="dev",
        no_sql_validation=True,
    )

    model_names: tuple[str, ...] = resolve_diff_model_names(
        project=project,
        select=test_case.select,
        exclude=test_case.exclude,
    )

    assert frozenset(model_names) == test_case.expected_model_names
