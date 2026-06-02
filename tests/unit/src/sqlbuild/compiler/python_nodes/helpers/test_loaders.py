"""Tests for loader conversion to internal Python-node models."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.discovery.types import LoaderConnectionMode
from sqlbuild.compiler.python_nodes.helpers.loaders import (
    build_python_loader_dependency_edges,
    build_python_loader_node,
)
from sqlbuild.compiler.python_nodes.models import (
    DiscoveredPythonLoaderMetadata,
    DiscoveredPythonNode,
    PythonNodeDependencyEdge,
)
from sqlbuild.compiler.python_nodes.types import PythonNodeKind
from sqlbuild.spec.models.source import SourceColumnEntry
from sqlbuild.spec.models.types import SourceWriteStrategy
from tests.unit.src.sqlbuild.compiler.python_nodes.helpers._test_types import (
    PythonLoaderNodeConversionTestCase,
)
from tests.unit.src.sqlbuild.compiler.python_nodes.helpers.helpers import (
    fetch_events,
    load_events,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PythonLoaderNodeConversionTestCase(
            description="preserves source loader metadata in internal Python-node view",
            expected_kind=PythonNodeKind.LOADER,
            expected_file_path=Path("/project/loaders/events.py"),
            expected_relative_path=Path("loaders/events.py"),
            expected_name="load_events",
            expected_depends_on=(fetch_events,),
            expected_dependency_edges=(("fetch_events", "load_events"),),
            expected_target="staging.events",
            expected_write_strategy="merge",
            expected_cursor_column="updated_at",
            expected_unique_key=("event_id", "updated_at"),
            expected_column_names=("event_id", "updated_at"),
            expected_contract="enforced",
            expected_connection_mode=LoaderConnectionMode.EXTERNAL,
        )
    ],
    ids=["preserves source loader metadata in internal Python-node view"],
)
def test_given_discovered_loader_when_building_python_node_then_preserves_loader_metadata(
    test_case: PythonLoaderNodeConversionTestCase,
) -> None:
    loader: DiscoveredLoaderFunction = DiscoveredLoaderFunction(
        file_path=test_case.expected_file_path,
        relative_path=test_case.expected_relative_path,
        name=test_case.expected_name,
        function=load_events,
        depends_on=(fetch_events,),
        destination=test_case.expected_target,
        write_strategy=SourceWriteStrategy(test_case.expected_write_strategy or "table"),
        cursor_column=test_case.expected_cursor_column,
        unique_key=test_case.expected_unique_key,
        columns=(
            SourceColumnEntry(name="event_id", type="BIGINT"),
            SourceColumnEntry(name="updated_at", type="TIMESTAMP"),
        ),
        contract=test_case.expected_contract,
        connection_mode=test_case.expected_connection_mode,
    )

    node: DiscoveredPythonNode = build_python_loader_node(loader=loader)
    dependency_edges: tuple[PythonNodeDependencyEdge, ...] = build_python_loader_dependency_edges(
        loaders=(
            DiscoveredLoaderFunction(
                file_path=Path("/project/loaders/events.py"),
                relative_path=Path("loaders/events.py"),
                name="fetch_events",
                function=fetch_events,
            ),
            loader,
        )
    )

    assert node.kind == test_case.expected_kind
    assert node.file_path == test_case.expected_file_path
    assert node.relative_path == test_case.expected_relative_path
    assert node.name == test_case.expected_name
    assert node.function is load_events
    assert node.depends_on == test_case.expected_depends_on
    assert node.tags == ()
    assert node.group is None
    assert node.description is None
    assert node.loader == DiscoveredPythonLoaderMetadata(
        destination=test_case.expected_target,
        write_strategy=SourceWriteStrategy(test_case.expected_write_strategy or "table"),
        cursor_column=test_case.expected_cursor_column,
        unique_key=test_case.expected_unique_key,
        columns=loader.columns,
        contract=test_case.expected_contract,
        connection_mode=test_case.expected_connection_mode,
    )
    assert node.loader is not None
    assert tuple(column.name for column in node.loader.columns) == test_case.expected_column_names
    assert tuple((edge.upstream_name, edge.downstream_name) for edge in dependency_edges) == (
        test_case.expected_dependency_edges
    )
    assert dependency_edges[0].upstream_function is fetch_events
    assert dependency_edges[0].downstream_function is load_events
