"""Internal Python-node discovery models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.discovery.types import LoaderConnectionMode
from sqlbuild.compiler.python_nodes.types import PythonNodeKind
from sqlbuild.shared.models import ColumnLineageRef, RetryPolicy
from sqlbuild.shared.types import PythonCheckSeverity
from sqlbuild.spec.models.source import SourceColumnEntry
from sqlbuild.spec.models.types import SourceWriteStrategy


@dataclass(frozen=True)
class DiscoveredPythonLoaderMetadata:
    """Loader-specific metadata carried by an internal Python loader node."""

    target: str | None = None
    write_strategy: SourceWriteStrategy | None = None
    cursor_column: str | None = None
    unique_key: tuple[str, ...] = field(default_factory=tuple)
    columns: tuple[SourceColumnEntry, ...] = field(default_factory=tuple)
    contract: str | None = None
    connection_mode: LoaderConnectionMode = LoaderConnectionMode.SQLBUILD


@dataclass(frozen=True)
class DiscoveredPythonTaskMetadata:
    """Task-specific metadata carried by an internal Python task node."""

    retry: RetryPolicy | None = None


@dataclass(frozen=True)
class DiscoveredPythonAssetMetadata:
    """Asset-specific metadata carried by an internal Python asset node."""

    columns: tuple[SourceColumnEntry, ...] = field(default_factory=tuple)
    column_lineage: dict[str, tuple[ColumnLineageRef, ...]] | None = None
    retry: RetryPolicy | None = None


@dataclass(frozen=True)
class DiscoveredPythonCheckMetadata:
    """Check-specific metadata carried by an internal Python check node."""

    severity: PythonCheckSeverity = PythonCheckSeverity.ERROR


@dataclass(frozen=True)
class DiscoveredPythonNode:
    """Shared internal view of a discovered Python DAG node."""

    kind: PythonNodeKind
    file_path: Path
    relative_path: Path
    name: str
    function: Callable[..., object]
    depends_on: tuple[Callable[..., object], ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    group: str | None = None
    description: str | None = None
    meta: dict[str, object] | None = None
    loader: DiscoveredPythonLoaderMetadata | None = None
    task: DiscoveredPythonTaskMetadata | None = None
    asset: DiscoveredPythonAssetMetadata | None = None
    check: DiscoveredPythonCheckMetadata | None = None


@dataclass(frozen=True)
class PythonNodeDependencyEdge:
    """Internal dependency edge between two discovered Python nodes."""

    upstream_name: str
    downstream_name: str
    upstream_function: Callable[..., object]
    downstream_function: Callable[..., object]


@dataclass(frozen=True)
class PythonNodeGraph:
    """Internal graph inventory for discovered executable Python nodes."""

    nodes: tuple[DiscoveredPythonNode, ...]
    dependency_edges: tuple[PythonNodeDependencyEdge, ...]
    upstream_deps: dict[str, tuple[str, ...]]
    downstream_deps: dict[str, tuple[str, ...]]
    tag_index: dict[str, frozenset[str]]
    nodes_by_name: dict[str, DiscoveredPythonNode]
    nodes_by_typed_selector: dict[str, DiscoveredPythonNode]


@dataclass(frozen=True)
class PythonSqlSelection:
    """Unified selector result across compiled SQL resources and Python nodes."""

    sql_keys: frozenset[CompiledObjectKey]
    python_node_names: frozenset[str]


@dataclass(frozen=True)
class DiscoveredPythonTaskNode:
    """Placeholder for future task-specific discovered node metadata."""

    node: DiscoveredPythonNode


@dataclass(frozen=True)
class DiscoveredPythonAssetNode:
    """Placeholder for future asset-specific discovered node metadata."""

    node: DiscoveredPythonNode


@dataclass(frozen=True)
class DiscoveredPythonCheckNode:
    """Placeholder for future check-specific discovered node metadata."""

    node: DiscoveredPythonNode
