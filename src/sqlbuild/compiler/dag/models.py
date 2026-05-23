"""Static DAG artifact models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DagTarget:
    """Warehouse identity for one SQLBuild DAG node."""

    database: str | None = None
    schema: str | None = None
    name: str | None = None
    qualified_name: str | None = None
    logical_database: str | None = None
    logical_schema: str | None = None


@dataclass(frozen=True)
class DagColumn:
    """Column metadata attached to one DAG node."""

    name: str
    type: str | None = None
    nullable: bool | None = None
    description: str | None = None
    meta: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DagFunctionArgument:
    """Function argument metadata attached to one function node."""

    name: str
    type: str


@dataclass(frozen=True)
class DagNode:
    """One asset-like node in the static SQLBuild DAG."""

    id: str
    kind: str
    name: str
    asset_key: tuple[str, ...]
    target: DagTarget | None = None
    path: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    meta: dict[str, object] = field(default_factory=dict)
    columns: tuple[DagColumn, ...] = field(default_factory=tuple)
    materialization_type: str | None = None
    language: str | None = None
    return_kind: str | None = None
    returns: str | None = None
    loader: str | None = None
    arguments: tuple[DagFunctionArgument, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DagEdge:
    """One static asset dependency edge."""

    from_id: str
    to_id: str


@dataclass(frozen=True)
class DagCheck:
    """One check definition attached to one or more DAG assets."""

    id: str
    kind: str
    name: str
    checked_asset_ids: tuple[str, ...]
    path: str | None = None
    severity: str | None = None
    attachment_kind: str | None = None
    attached_target_name: str | None = None
    attached_column_name: str | None = None
    mode: str | None = None
    assertion_names: tuple[str, ...] = field(default_factory=tuple)
    expected_model_names: tuple[str, ...] = field(default_factory=tuple)
    graph_asset_ids: tuple[str, ...] = field(default_factory=tuple)
    fixture_refs: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DagArtifact:
    """Complete static SQLBuild DAG artifact."""

    version: int
    project_name: str
    nodes: tuple[DagNode, ...]
    edges: tuple[DagEdge, ...]
    checks: tuple[DagCheck, ...]
