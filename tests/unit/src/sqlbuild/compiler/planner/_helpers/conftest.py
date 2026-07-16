from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledProject,
)
from sqlbuild.compiler.planner._helpers.graph.core import (
    build_downstream_deps,
    build_execution_upstream_deps,
)
from sqlbuild.compiler.planner.main.selection.build_model_path_index import (
    build_model_path_index,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.helpers import (
    build_test_project,
    model_key,
)


@pytest.fixture
def diamond_graph() -> tuple[
    dict[str, CompiledObjectKey],
    dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
]:
    project: CompiledProject = build_test_project(
        model_deps={
            "orders": ("raw_orders",),
            "customers": ("raw_customers",),
            "joined": ("orders", "customers"),
        },
        source_names=("raw_orders", "raw_customers"),
        seed_names=("codes",),
    )
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = (
        build_execution_upstream_deps(project)
    )
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_downstream_deps(
        upstream
    )
    all_keys: dict[str, CompiledObjectKey] = {key.name: key for key in upstream}
    return all_keys, upstream, downstream


@pytest.fixture
def diamond_tag_index() -> dict[str, frozenset[CompiledObjectKey]]:
    return {
        "nightly": frozenset({model_key("orders"), model_key("joined")}),
        "staging": frozenset({model_key("orders")}),
    }


@pytest.fixture
def path_graph() -> tuple[
    dict[str, CompiledObjectKey],
    dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    dict[CompiledObjectKey, str],
]:
    project: CompiledProject = build_test_project(
        model_deps={
            "stg_orders": ("raw_orders",),
            "stg_customers": ("raw_customers",),
            "stg_deep": ("raw_orders",),
            "int_enriched": ("stg_orders", "stg_customers"),
            "fact_orders": ("int_enriched",),
        },
        model_paths={
            "stg_orders": "models/staging/stg_orders.sql",
            "stg_customers": "models/staging/stg_customers.sql",
            "stg_deep": "models/staging/raw/stg_deep.sql",
            "int_enriched": "models/intermediate/int_enriched.sql",
            "fact_orders": "models/marts/fact_orders.sql",
        },
        source_names=("raw_orders", "raw_customers"),
    )
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = (
        build_execution_upstream_deps(project)
    )
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_downstream_deps(
        upstream
    )
    all_keys: dict[str, CompiledObjectKey] = {key.name: key for key in upstream}
    path_idx: dict[CompiledObjectKey, str] = build_model_path_index(project)
    return all_keys, upstream, downstream, path_idx
