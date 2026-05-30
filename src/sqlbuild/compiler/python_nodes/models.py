"""Internal Python-node discovery models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.compiler.discovery.types import LoaderConnectionMode
from sqlbuild.compiler.python_nodes.types import PythonNodeKind
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
    loader: DiscoveredPythonLoaderMetadata | None = None


@dataclass(frozen=True)
class PythonNodeDependencyEdge:
    """Internal dependency edge between two discovered Python nodes."""

    upstream_name: str
    downstream_name: str
    upstream_function: Callable[..., object]
    downstream_function: Callable[..., object]


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
