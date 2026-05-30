"""Tests for source-load node planning helpers."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models.core import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.helpers.loader_dag import (
    build_intermediate_source_map,
    expand_selected_loader_dependencies,
)
from sqlbuild.compiler.planner.helpers.source_load_nodes import (
    build_source_load_entries,
    build_source_load_map,
)
from sqlbuild.compiler.planner.models import SourceLoadPlanEntry
from sqlbuild.shared.types import ExecutionResourceKind
from sqlbuild.spec.models.source import SourceEntry
from sqlbuild.spec.models.types import SourceWriteStrategy
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    LoaderDagExpansionTestCase,
    SourceLoadNodesTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    build_source_load_nodes_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SourceLoadNodesTestCase(
            description="builds terminal and intermediate source-load entries",
            expected_map_names=("fetch_orders", "raw_orders"),
            expected_entries=(
                SourceLoadPlanEntry(
                    key=CompiledObjectKey(CompiledResourceType.SOURCE, "fetch_orders"),
                    name="fetch_orders",
                    loader="fetch_orders",
                    target="staging_fetch_orders",
                    resource_kind=ExecutionResourceKind.LOADER,
                    write_strategy=SourceWriteStrategy.TABLE,
                    cursor_column=None,
                    unique_key=(),
                    is_reload=True,
                ),
                SourceLoadPlanEntry(
                    key=CompiledObjectKey(CompiledResourceType.SOURCE, "raw_orders"),
                    name="raw_orders",
                    loader="load_orders",
                    target="orders",
                    resource_kind=ExecutionResourceKind.SOURCE,
                    write_strategy=SourceWriteStrategy.MERGE,
                    cursor_column="updated_at",
                    unique_key=("order_id",),
                    is_reload=True,
                ),
            ),
        )
    ],
    ids=["builds terminal and intermediate source-load entries"],
)
def test_given_selected_source_load_keys_when_building_entries_then_returns_ordered_load_nodes(
    test_case: SourceLoadNodesTestCase,
) -> None:
    project: CompiledProject = build_source_load_nodes_project()
    selected_keys: frozenset[CompiledObjectKey] = frozenset(
        entry.key for entry in test_case.expected_entries
    )
    execution_order: tuple[CompiledObjectKey, ...] = tuple(
        entry.key for entry in test_case.expected_entries
    )

    source_map: dict[str, SourceEntry] = build_source_load_map(
        project=project,
        selected_keys=selected_keys,
    )
    entries: tuple[SourceLoadPlanEntry, ...] = build_source_load_entries(
        execution_order=execution_order,
        selected_keys=selected_keys,
        source_map=source_map,
        is_reload=True,
    )

    assert tuple(sorted(source_map)) == test_case.expected_map_names
    assert entries == test_case.expected_entries


@pytest.mark.parametrize(
    "test_case",
    [
        LoaderDagExpansionTestCase(
            description="adds intermediate loader dependencies for selected terminal source",
            selected_names=frozenset({"raw_orders"}),
            expected_selected_names=frozenset({"fetch_orders", "raw_orders"}),
            expected_upstream_names={
                "raw_orders": ("fetch_orders",),
                "fetch_orders": (),
            },
            expected_intermediate_source_names=("fetch_orders",),
            expected_intermediate_loader_flags=(True,),
        )
    ],
    ids=["adds intermediate loader dependencies for selected terminal source"],
)
def test_given_terminal_source_when_expanding_loader_deps_then_adds_intermediate_source(
    test_case: LoaderDagExpansionTestCase,
) -> None:
    project: CompiledProject = build_source_load_nodes_project()
    selected_keys: frozenset[CompiledObjectKey] = frozenset(
        CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name=name)
        for name in test_case.selected_names
    )

    expanded_selected, upstream_deps = expand_selected_loader_dependencies(
        project=project,
        selected_keys=selected_keys,
        upstream_deps={},
    )
    intermediate_sources: dict[str, SourceEntry] = build_intermediate_source_map(
        project=project,
        selected_keys=expanded_selected,
    )

    assert frozenset(key.name for key in expanded_selected) == test_case.expected_selected_names
    assert {
        key.name: tuple(dep.name for dep in deps) for key, deps in upstream_deps.items()
    } == test_case.expected_upstream_names
    assert tuple(intermediate_sources) == test_case.expected_intermediate_source_names
    assert (
        tuple(
            source.meta.get("sqlbuild_loader_node") is True
            for source in intermediate_sources.values()
        )
        == test_case.expected_intermediate_loader_flags
    )
