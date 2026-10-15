"""Internal Python-node discovery models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild._native import (
    DiscoveredPythonAssetMetadata,
    DiscoveredPythonCheckMetadata,
    DiscoveredPythonLoaderMetadata,
    DiscoveredPythonTaskMetadata,
    PythonNodeDependencyEdge,
)
from sqlbuild.compiler.discovery.models import DiscoveredProviderUsage
from sqlbuild.compiler.python_nodes.types import PythonNodeKind
from sqlbuild.python_nodes.models import SqlResourceRef


@dataclass(frozen=True)
class DiscoveredPythonNode:
    """Shared internal view of a discovered Python DAG node."""

    kind: PythonNodeKind
    file_path: Path
    relative_path: Path
    name: str
    function: Callable[..., object]
    depends_on: tuple[Callable[..., object] | SqlResourceRef, ...] = field(default_factory=tuple)
    sql_deps: tuple[SqlResourceRef, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    group: str | None = None
    description: str | None = None
    meta: dict[str, object] | None = None
    provider_usages: tuple[DiscoveredProviderUsage, ...] = field(default_factory=tuple)
    loader: DiscoveredPythonLoaderMetadata | None = None
    task: DiscoveredPythonTaskMetadata | None = None
    asset: DiscoveredPythonAssetMetadata | None = None
    check: DiscoveredPythonCheckMetadata | None = None
    identity: PythonNodeIdentity | None = None


@dataclass(frozen=True)
class PythonNodeGraph:
    """Internal graph inventory for discovered executable Python nodes."""

    nodes: tuple[DiscoveredPythonNode, ...]
    dependency_edges: tuple[PythonNodeDependencyEdge, ...]
    upstream_deps: dict[str, tuple[str, ...]]
    downstream_deps: dict[str, tuple[str, ...]]
    tag_index: dict[str, frozenset[str]]
    path_index: dict[str, str]
    nodes_by_name: dict[str, DiscoveredPythonNode]
    nodes_by_typed_selector: dict[str, DiscoveredPythonNode]

    def selected_sql_refs(self, *, selected_names: frozenset[str]) -> frozenset[SqlResourceRef]:
        """Return SQL references required by a selected Python-node closure."""

        refs: set[SqlResourceRef] = set()
        pending: list[str] = list(selected_names)
        visited: set[str] = set()
        while pending:
            node_name: str = pending.pop()
            if node_name in visited:
                continue
            visited.add(node_name)
            node: DiscoveredPythonNode | None = self.nodes_by_name.get(node_name)
            if node is not None:
                refs.update(node.sql_deps)
            pending.extend(self.upstream_deps.get(node_name, ()))
        return frozenset(refs)


@dataclass(frozen=True)
class PythonSqlRunLifecyclePlan:
    """Lifecycle-aware run classification for SQL resources and Python nodes."""

    ingress_python_node_names: frozenset[str]
    ingress_loader_names: frozenset[str]
    read_side_python_node_names: frozenset[str]


@dataclass(frozen=True)
class PythonIdentityDependency:
    """One first-party Python source object included in a Python node identity."""

    kind: str
    module: str
    qualname: str
    source_path: str
    source_hash: str
    source_text: str


@dataclass(frozen=True)
class PythonNodeIdentity:
    """Read-only identity metadata for a SQLBuild Python node."""

    node_type: str
    node_name: str
    source_path: str
    source_hash: str
    definition_hash: str
    version_hash: str
    dependencies: tuple[PythonIdentityDependency, ...] = field(default_factory=tuple)
    definition_json: str = "{}"
    metadata_json: str = "{}"
