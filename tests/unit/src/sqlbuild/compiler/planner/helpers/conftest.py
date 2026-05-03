from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.planner.helpers.graph import (
    build_downstream_deps,
    build_upstream_deps,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import build_test_project


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
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_upstream_deps(project)
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_downstream_deps(
        upstream
    )
    all_keys: dict[str, CompiledObjectKey] = {key.name: key for key in upstream}
    return all_keys, upstream, downstream
