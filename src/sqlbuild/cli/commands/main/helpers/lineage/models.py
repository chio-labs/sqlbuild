"""Lineage command models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.compiler.compile.models import CompiledObjectKey


@dataclass(frozen=True)
class LineageNode:
    """One displayable lineage graph node."""

    key: CompiledObjectKey
    relative_path: str | None = None
    qualified_name: str | None = None


@dataclass(frozen=True)
class LineageGraph:
    """Selected lineage graph slice."""

    nodes: tuple[LineageNode, ...]
    edges: tuple[tuple[CompiledObjectKey, CompiledObjectKey], ...]
    focus_keys: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)
    direction: str | None = None


@dataclass(frozen=True)
class LineageSelectionAnchors:
    """Selector anchors used for optional post-selection depth trimming."""

    upstream: frozenset[CompiledObjectKey] = field(default_factory=frozenset)
    downstream: frozenset[CompiledObjectKey] = field(default_factory=frozenset)
    retained: frozenset[CompiledObjectKey] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ParsedLineageSelector:
    """One parsed non-path lineage selector."""

    kind: str
    value: str
    upstream: bool = False
    downstream: bool = False


@dataclass(frozen=True)
class ParsedLineagePathSelector:
    """One parsed path-between lineage selector."""

    start_name: str
    end_name: str
    upstream: bool = False
    downstream: bool = False
