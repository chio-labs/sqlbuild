"""Column lineage result models and project graph."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import cast

from sqlbuild.compiler.compile.models import (
    CompactLineageFacts,
    CompiledLineageColumnFact,
    CompiledLineageSourceFact,
)
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
class DirectSemanticColumnUse:
    """One direct non-projection use of a resolved resource column."""

    consumer_model: str
    context: str
    expression_sql: str
    source: QualifiedLineageColumn
    confidence: ColumnLineageConfidence = ColumnLineageConfidence.UNKNOWN
    line: int | None = None
    column: int | None = None


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


_CompactEdgeRecord = tuple[
    CompiledLineageSourceFact | ColumnLineageSource,
    str,
    str,
    ColumnTransformKind,
    ColumnLineageConfidence,
]
_IndexedEdgeRecord = tuple[
    CompactLineageFacts,
    tuple[int, int, int],
    str,
    str,
    int,
    int,
]
_EdgeRecord = ColumnLineageEdge | _CompactEdgeRecord | _IndexedEdgeRecord


class ProjectColumnLineage:
    """Project-level column lineage graph with lazily materialized public views."""

    def __init__(
        self,
        *,
        models: dict[str, ModelColumnLineage],
        edges: tuple[ColumnLineageEdge, ...],
    ) -> None:
        self._models: dict[str, ModelColumnLineage] = models
        self._compact_models: dict[str, tuple[Sequence[CompiledLineageColumnFact], bool]] = {}
        self._model_order: tuple[str, ...] = tuple(models)
        self._edges: tuple[ColumnLineageEdge, ...] | None = edges
        self._edge_records: tuple[_EdgeRecord, ...] = edges
        self._edge_cache: dict[
            tuple[str, str, str, str, str, ColumnTransformKind, ColumnLineageConfidence],
            ColumnLineageEdge,
        ] = {}
        self._edge_counts_by_target_model: dict[str, int] = {}
        self._indexes_initialized: bool = False
        self._initialize_indexes()

    @classmethod
    def from_fast_facts(
        cls,
        *,
        models: dict[str, ModelColumnLineage],
        compact_models: dict[str, tuple[Sequence[CompiledLineageColumnFact], bool]],
        model_order: tuple[str, ...],
    ) -> ProjectColumnLineage:
        """Build indexed project lineage without expanding compact analysis facts."""

        result: ProjectColumnLineage = cls(models=models, edges=())
        result._compact_models = compact_models
        result._model_order = model_order
        result._edges = None
        result._edge_records = ()
        result._indexes_initialized = False
        result._edge_counts_by_target_model = {
            model_name: (
                sum(len(row[3]) for row in compact[0].rows)
                if isinstance(compact[0], CompactLineageFacts)
                else sum(len(column.upstream_columns) for column in compact[0])
            )
            for model_name in model_order
            if (compact := compact_models.get(model_name)) is not None
        }
        result._edge_counts_by_target_model.update(
            {
                model_name: sum(len(column.upstream_columns) for column in model.columns)
                for model_name, model in models.items()
            }
        )
        return result

    def _build_fast_edge_records(
        self,
    ) -> tuple[_CompactEdgeRecord | _IndexedEdgeRecord, ...]:
        records: list[_CompactEdgeRecord | _IndexedEdgeRecord] = []
        for model_name in self._model_order:
            compact: tuple[Sequence[CompiledLineageColumnFact], bool] | None = (
                self._compact_models.get(model_name)
            )
            if compact is not None:
                columns = compact[0]
                if isinstance(columns, CompactLineageFacts):
                    for name_index, transform_code, confidence_code, sources in columns.rows:
                        output_column = columns.string_pool[name_index]
                        records.extend(
                            (
                                columns,
                                source,
                                model_name,
                                output_column,
                                transform_code,
                                confidence_code,
                            )
                            for source in sources
                        )
                else:
                    for column in columns:
                        records.extend(
                            (
                                source,
                                model_name,
                                column.output_column,
                                column.transform_kind,
                                column.confidence,
                            )
                            for source in column.upstream_columns
                        )
                continue
            model: ModelColumnLineage | None = self._models.get(model_name)
            if model is None:
                continue
            for column in model.columns:
                records.extend(
                    (
                        source,
                        model_name,
                        column.output_column,
                        column.transform_kind,
                        column.confidence,
                    )
                    for source in column.upstream_columns
                )
        return tuple(records)

    @property
    def models(self) -> dict[str, ModelColumnLineage]:
        """Return model lineage, expanding compact model facts on first access."""

        if self._compact_models:
            for model_name in self._model_order:
                compact = self._compact_models.get(model_name)
                if compact is not None and model_name not in self._models:
                    self._models[model_name] = _model_lineage_from_compact_facts(
                        model_name=model_name,
                        columns=compact[0],
                        has_star=compact[1],
                    )
            self._compact_models = {}
        return self._models

    @property
    def edges(self) -> tuple[ColumnLineageEdge, ...]:
        """Return all graph edges, expanding compact edge records on first access."""

        if self._edges is None:
            self._ensure_indexes()
            self._edges = tuple(self._materialize_edge(record) for record in self._edge_records)
        return self._edges

    def has_model(self, model_name: str) -> bool:
        """Return whether model lineage is available without expanding its columns."""

        return model_name in self._models or model_name in self._compact_models

    def model_has_star(self, model_name: str) -> bool:
        """Return whether model lineage retains unresolved root-star uncertainty."""

        compact = self._compact_models.get(model_name)
        if compact is not None:
            return compact[1]
        model = self._models.get(model_name)
        return model.has_star if model is not None else False

    def edge_count_targeting(self, model_name: str) -> int:
        """Return a target model's direct edge count without expanding edge objects."""

        return self._edge_counts_by_target_model.get(
            model_name,
            len(self._edge_records_by_target_model.get(model_name, ())),
        )

    def _initialize_indexes(self) -> None:
        by_target_model: dict[str, list[_EdgeRecord]] = defaultdict(list)
        by_source_resource: dict[str, list[_EdgeRecord]] = defaultdict(list)
        by_target_column: dict[tuple[str, str], _EdgeRecord] = {}
        for record in self._edge_records:
            source_name, target_name, target_column = _edge_record_identity(record)
            by_target_model[target_name].append(record)
            by_source_resource[source_name].append(record)
            by_target_column.setdefault((target_name, target_column), record)
        self._edge_records_by_target_model: dict[str, tuple[_EdgeRecord, ...]] = {
            key: tuple(value) for key, value in by_target_model.items()
        }
        self._edge_records_by_source_resource: dict[str, tuple[_EdgeRecord, ...]] = {
            key: tuple(value) for key, value in by_source_resource.items()
        }
        self._edge_record_by_target_column: dict[tuple[str, str], _EdgeRecord] = by_target_column
        self._edge_counts_by_target_model = {
            key: len(value) for key, value in self._edge_records_by_target_model.items()
        }
        self._indexes_initialized = True

    def _ensure_indexes(self) -> None:
        if self._indexes_initialized:
            return
        self._edge_records = self._build_fast_edge_records()
        self._initialize_indexes()

    def _materialize_edge(self, record: _EdgeRecord) -> ColumnLineageEdge:
        if isinstance(record, ColumnLineageEdge):
            return record
        (
            resource_type,
            resource_name,
            source_column,
            target_model,
            target_column,
            transform_kind,
            confidence,
        ) = _edge_record_values(record)
        key = (
            str(resource_type),
            resource_name,
            source_column,
            target_model,
            target_column,
            transform_kind,
            confidence,
        )
        cached = self._edge_cache.get(key)
        if cached is not None:
            return cached
        edge = ColumnLineageEdge(
            source=QualifiedLineageColumn(
                resource_type=resource_type,
                resource_name=resource_name,
                column_name=source_column,
            ),
            target=QualifiedLineageColumn(
                resource_type=CompiledResourceType.MODEL,
                resource_name=target_model,
                column_name=target_column,
            ),
            transform_kind=transform_kind,
            confidence=confidence,
        )
        self._edge_cache[key] = edge
        return edge

    def edges_targeting(self, model_name: str) -> tuple[ColumnLineageEdge, ...]:
        """Return edges whose target model is `model_name`."""

        self._ensure_indexes()
        return tuple(
            self._materialize_edge(record)
            for record in self._edge_records_by_target_model.get(model_name, ())
        )

    def producing_edge(
        self,
        *,
        model_name: str,
        column_name: str,
    ) -> ColumnLineageEdge | None:
        """Return the first edge that produces `model_name.column_name`."""

        self._ensure_indexes()
        record = self._edge_record_by_target_column.get((model_name, column_name))
        return self._materialize_edge(record) if record is not None else None

    def edges_sourced_from(self, resource_name: str) -> tuple[ColumnLineageEdge, ...]:
        """Return edges whose source resource is `resource_name`."""

        self._ensure_indexes()
        return tuple(
            self._materialize_edge(record)
            for record in self._edge_records_by_source_resource.get(resource_name, ())
        )

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

    def __repr__(self) -> str:
        return f"ProjectColumnLineage(models={self.models!r}, edges={self.edges!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ProjectColumnLineage):
            return NotImplemented
        return self.models == other.models and self.edges == other.edges


def _edge_record_identity(record: _EdgeRecord) -> tuple[str, str, str]:
    if isinstance(record, ColumnLineageEdge):
        return (
            record.source.resource_name,
            record.target.resource_name,
            record.target.column_name,
        )
    _, resource_name, _, target_model, target_column, _, _ = _edge_record_values(record)
    return resource_name, target_model, target_column


def _edge_record_values(
    record: _CompactEdgeRecord | _IndexedEdgeRecord,
) -> tuple[
    CompiledResourceType | str,
    str,
    str,
    str,
    str,
    ColumnTransformKind,
    ColumnLineageConfidence,
]:
    if len(record) == 6:
        facts, source, target_model, target_column, transform_code, confidence_code = cast(
            _IndexedEdgeRecord, record
        )
        return (
            facts.string_pool[source[0]],
            facts.resource_name(source[1]),
            facts.string_pool[source[2]],
            target_model,
            target_column,
            facts.transform_kind(transform_code),
            facts.confidence(confidence_code),
        )
    source, target_model, target_column, transform_kind, confidence = cast(
        _CompactEdgeRecord, record
    )
    return (
        source.resource_type,
        source.resource_name,
        source.column_name,
        target_model,
        target_column,
        transform_kind,
        confidence,
    )


def _model_lineage_from_compact_facts(
    *,
    model_name: str,
    columns: Sequence[CompiledLineageColumnFact],
    has_star: bool,
) -> ModelColumnLineage:
    return ModelColumnLineage(
        model_name=model_name,
        columns=tuple(
            ColumnLineage(
                output_column=column.output_column,
                transform_kind=column.transform_kind,
                expression_sql=None,
                upstream_columns=tuple(
                    ColumnLineageSource(
                        resource_type=source.resource_type,
                        resource_name=source.resource_name,
                        column_name=source.column_name,
                    )
                    for source in column.upstream_columns
                ),
                nullability=InferredNullability.UNKNOWN,
                confidence=column.confidence,
            )
            for column in columns
        ),
        has_star=has_star,
    )
