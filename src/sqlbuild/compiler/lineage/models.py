"""Column lineage result models and project graph."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.types import (
    ColumnLineageConfidence,
    ColumnTransformKind,
    InferredNullability,
)


@dataclass(frozen=True)
class PhysicalResource:
    """A physical SQL identifier mapped to its SQLBuild resource."""

    resource_type: CompiledResourceType
    resource_name: str
    physical_name: str


@dataclass(frozen=True)
class QualifiedLineageColumn:
    """A resource-qualified column in the collapsed SQLBuild lineage graph."""

    resource_type: CompiledResourceType | str
    resource_name: str
    column_name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource_type", CompiledResourceType(self.resource_type))


@dataclass(frozen=True)
class ColumnLineageSource:
    """One upstream column dependency for an output column."""

    resource_type: CompiledResourceType | str
    resource_name: str
    column_name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource_type", CompiledResourceType(self.resource_type))

    def as_qualified_column(self) -> QualifiedLineageColumn:
        return QualifiedLineageColumn(
            resource_type=self.resource_type,
            resource_name=self.resource_name,
            column_name=self.column_name,
        )


@dataclass(frozen=True)
class ColumnLineageNode:
    """One internal SQL analysis lineage graph node."""

    id: str
    name: str
    expression_sql: str | None = None
    source_sql: str | None = None
    resource_type: CompiledResourceType | str | None = None
    resource_name: str | None = None
    scope_name: str | None = None

    def __post_init__(self) -> None:
        if self.resource_type is not None:
            object.__setattr__(self, "resource_type", CompiledResourceType(self.resource_type))


@dataclass(frozen=True)
class InternalColumnLineageEdge:
    """One edge in the internal SQL analysis lineage graph."""

    upstream_node_id: str
    downstream_node_id: str


@dataclass(frozen=True)
class ColumnLineageEdge:
    """One collapsed SQLBuild lineage graph edge."""

    source: QualifiedLineageColumn
    target: QualifiedLineageColumn
    transform_kind: ColumnTransformKind = ColumnTransformKind.UNKNOWN
    confidence: ColumnLineageConfidence = ColumnLineageConfidence.UNKNOWN


@dataclass(frozen=True)
class ColumnLineage:
    """Lineage for one output column in one model."""

    output_column: str
    transform_kind: ColumnTransformKind
    expression_sql: str | None
    upstream_columns: tuple[ColumnLineageSource, ...]
    nullability: InferredNullability = InferredNullability.UNKNOWN
    nodes: tuple[ColumnLineageNode, ...] = field(default_factory=tuple)
    edges: tuple[InternalColumnLineageEdge, ...] = field(default_factory=tuple)
    confidence: ColumnLineageConfidence = ColumnLineageConfidence.UNKNOWN


@dataclass(frozen=True)
class ModelColumnLineage:
    """Column lineage extracted for one compiled model."""

    model_name: str
    columns: tuple[ColumnLineage, ...]
    has_star: bool = False


@dataclass(frozen=True)
class ProjectColumnLineage:
    """Project-level column lineage graph with traversal indexes."""

    models: dict[str, ModelColumnLineage]
    edges: tuple[ColumnLineageEdge, ...]
    _edges_by_target_model: dict[str, tuple[ColumnLineageEdge, ...]] = field(
        init=False,
        repr=False,
    )
    _edges_by_source_resource: dict[str, tuple[ColumnLineageEdge, ...]] = field(
        init=False,
        repr=False,
    )
    _edge_by_target_column: dict[tuple[str, str], ColumnLineageEdge] = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        by_target_model: dict[str, list[ColumnLineageEdge]] = defaultdict(list)
        by_source_resource: dict[str, list[ColumnLineageEdge]] = defaultdict(list)
        by_target_column: dict[tuple[str, str], ColumnLineageEdge] = {}

        for edge in self.edges:
            by_target_model[edge.target.resource_name].append(edge)
            by_source_resource[edge.source.resource_name].append(edge)
            by_target_column.setdefault(
                (edge.target.resource_name, edge.target.column_name),
                edge,
            )

        object.__setattr__(
            self,
            "_edges_by_target_model",
            {key: tuple(value) for key, value in by_target_model.items()},
        )
        object.__setattr__(
            self,
            "_edges_by_source_resource",
            {key: tuple(value) for key, value in by_source_resource.items()},
        )
        object.__setattr__(self, "_edge_by_target_column", by_target_column)

    def edges_targeting(self, model_name: str) -> tuple[ColumnLineageEdge, ...]:
        """Return edges whose target model is `model_name`."""

        return self._edges_by_target_model.get(model_name, ())

    def producing_edge(
        self,
        *,
        model_name: str,
        column_name: str,
    ) -> ColumnLineageEdge | None:
        """Return the first edge that produces `model_name.column_name`."""

        return self._edge_by_target_column.get((model_name, column_name))

    def edges_sourced_from(self, resource_name: str) -> tuple[ColumnLineageEdge, ...]:
        """Return edges whose source resource is `resource_name`."""

        return self._edges_by_source_resource.get(resource_name, ())

    def column_consumers(
        self,
        *,
        resource_name: str,
        column_name: str,
    ) -> tuple[ColumnLineageEdge, ...]:
        """Return direct downstream consumers of `resource_name.column_name`."""

        return tuple(
            edge
            for edge in self.edges_sourced_from(resource_name)
            if edge.source.column_name == column_name
        )

    def trace_column(
        self,
        *,
        model_name: str,
        column_name: str,
    ) -> tuple[ColumnLineageEdge, ...]:
        """Trace a model column upstream through project lineage edges."""

        result: list[ColumnLineageEdge] = []
        stack: list[tuple[str, str]] = [(model_name, column_name)]
        visited: set[tuple[str, str]] = set()

        while stack:
            current_model, current_column = stack.pop()
            if (current_model, current_column) in visited:
                continue
            visited.add((current_model, current_column))
            for edge in self.edges_targeting(current_model):
                if edge.target.column_name == current_column:
                    result.append(edge)
                    stack.append((edge.source.resource_name, edge.source.column_name))

        return tuple(result)

    def trace_column_downstream(
        self,
        *,
        resource_name: str,
        column_name: str,
    ) -> tuple[ColumnLineageEdge, ...]:
        """Trace a resource column downstream through project lineage edges."""

        result: list[ColumnLineageEdge] = []
        stack: list[tuple[str, str]] = [(resource_name, column_name)]
        visited: set[tuple[str, str]] = set()

        while stack:
            current_resource, current_column = stack.pop()
            if (current_resource, current_column) in visited:
                continue
            visited.add((current_resource, current_column))
            for edge in self.edges_sourced_from(current_resource):
                if edge.source.column_name == current_column:
                    result.append(edge)
                    stack.append((edge.target.resource_name, edge.target.column_name))

        return tuple(result)
