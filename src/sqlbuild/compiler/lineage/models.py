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
from sqlbuild.compiler.lineage.constants import INDEXED_EDGE_RECORD_LENGTH
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
    confidence: ColumnLineageConfidence = ColumnLineageConfidence.UNKNOWN


@dataclass(frozen=True)
class ModelColumnLineage:
    """Column lineage extracted for one compiled model."""

    model_name: str
    columns: tuple[ColumnLineage, ...]
    has_star: bool = False


@dataclass(frozen=True, init=False)
class ProjectColumnLineage:
    """Project-level column lineage graph with lazily materialized public views."""

    _models: dict[str, ModelColumnLineage] = field(init=False, repr=False)
    _compact_models: dict[str, tuple[Sequence[CompiledLineageColumnFact], bool]] = field(
        init=False, repr=False
    )
    _model_order: tuple[str, ...] = field(init=False, repr=False)
    _edges: tuple[ColumnLineageEdge, ...] | None = field(init=False, repr=False)
    _edge_records: tuple[object, ...] = field(init=False, repr=False)
    _edge_cache: dict[
        tuple[str, str, str, str, str, ColumnTransformKind, ColumnLineageConfidence],
        ColumnLineageEdge,
    ] = field(init=False, repr=False)
    _edge_counts_by_target_model: dict[str, int] = field(init=False, repr=False)
    _indexes_initialized: bool = field(init=False, repr=False)
    _edge_records_by_target_model: dict[str, tuple[object, ...]] = field(init=False, repr=False)
    _edge_records_by_source_resource: dict[str, tuple[object, ...]] = field(init=False, repr=False)
    _edge_record_by_target_column: dict[tuple[str, str], object] = field(init=False, repr=False)

    def __init__(
        self,
        *,
        models: dict[str, ModelColumnLineage],
        edges: tuple[ColumnLineageEdge, ...],
    ) -> None:
        object.__setattr__(self, "_models", models)
        object.__setattr__(self, "_compact_models", {})
        object.__setattr__(self, "_model_order", tuple(models))
        object.__setattr__(self, "_edges", edges)
        object.__setattr__(self, "_edge_records", edges)
        object.__setattr__(self, "_edge_cache", {})
        object.__setattr__(self, "_edge_counts_by_target_model", {})
        object.__setattr__(self, "_indexes_initialized", False)
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
        object.__setattr__(result, "_compact_models", compact_models)
        object.__setattr__(result, "_model_order", model_order)
        object.__setattr__(result, "_edges", None)
        object.__setattr__(result, "_edge_records", ())
        object.__setattr__(result, "_indexes_initialized", False)
        edge_counts: dict[str, int] = {}
        for model_name in model_order:
            compact: tuple[Sequence[CompiledLineageColumnFact], bool] | None = compact_models.get(
                model_name
            )
            if compact is None:
                continue
            compact_columns: Sequence[CompiledLineageColumnFact] = compact[0]
            if isinstance(compact_columns, CompactLineageFacts):
                edge_counts[model_name] = sum(len(row[3]) for row in compact_columns.rows)
            else:
                edge_counts[model_name] = sum(
                    len(column.upstream_columns) for column in compact_columns
                )
        for model_name, model in models.items():
            edge_counts[model_name] = sum(len(column.upstream_columns) for column in model.columns)
        object.__setattr__(result, "_edge_counts_by_target_model", edge_counts)
        return result

    def _build_fast_edge_records(
        self,
    ) -> tuple[object, ...]:
        records: list[object] = []
        for model_name in self._model_order:
            compact: tuple[Sequence[CompiledLineageColumnFact], bool] | None = (
                self._compact_models.get(model_name)
            )
            if compact is not None:
                columns: Sequence[CompiledLineageColumnFact] = compact[0]
                if isinstance(columns, CompactLineageFacts):
                    for name_index, transform_code, confidence_code, sources in columns.rows:
                        output_column: str = columns.string_pool[name_index]
                        for source in sources:
                            records.append(
                                (
                                    columns,
                                    source,
                                    model_name,
                                    output_column,
                                    transform_code,
                                    confidence_code,
                                )
                            )
                else:
                    for column in columns:
                        for source in column.upstream_columns:
                            records.append(
                                (
                                    source,
                                    model_name,
                                    column.output_column,
                                    column.transform_kind,
                                    column.confidence,
                                )
                            )
                continue
            model: ModelColumnLineage | None = self._models.get(model_name)
            if model is None:
                continue
            for column in model.columns:
                for source in column.upstream_columns:
                    records.append(
                        (
                            source,
                            model_name,
                            column.output_column,
                            column.transform_kind,
                            column.confidence,
                        )
                    )
        return tuple(records)

    @property
    def models(self) -> dict[str, ModelColumnLineage]:
        """Return model lineage, expanding compact model facts on first access."""

        if self._compact_models:
            for model_name in self._model_order:
                compact: tuple[Sequence[CompiledLineageColumnFact], bool] | None = (
                    self._compact_models.get(model_name)
                )
                if compact is not None and model_name not in self._models:
                    self._models[model_name] = self._model_lineage_from_compact_facts(
                        model_name=model_name,
                        columns=compact[0],
                        has_star=compact[1],
                    )
            object.__setattr__(self, "_compact_models", {})
        return self._models

    @property
    def edges(self) -> tuple[ColumnLineageEdge, ...]:
        """Return all graph edges, expanding compact edge records on first access."""

        if self._edges is None:
            self._ensure_indexes()
            object.__setattr__(
                self,
                "_edges",
                tuple(self._materialize_edge(record) for record in self._edge_records),
            )
        edges: tuple[ColumnLineageEdge, ...] | None = self._edges
        if edges is None:
            return ()
        return edges

    def has_model(self, model_name: str) -> bool:
        """Return whether model lineage is available without expanding its columns."""

        return model_name in self._models or model_name in self._compact_models

    def model_has_star(self, model_name: str) -> bool:
        """Return whether model lineage retains unresolved root-star uncertainty."""

        compact: tuple[Sequence[CompiledLineageColumnFact], bool] | None = self._compact_models.get(
            model_name
        )
        if compact is not None:
            return compact[1]
        model: ModelColumnLineage | None = self._models.get(model_name)
        return model.has_star if model is not None else False

    def edge_count_targeting(self, model_name: str) -> int:
        """Return a target model's direct edge count without expanding edge objects."""

        return self._edge_counts_by_target_model.get(
            model_name,
            len(self._edge_records_by_target_model.get(model_name, ())),
        )

    def _initialize_indexes(self) -> None:
        by_target_model: dict[str, list[object]] = defaultdict(list)
        by_source_resource: dict[str, list[object]] = defaultdict(list)
        by_target_column: dict[tuple[str, str], object] = {}
        for record in self._edge_records:
            source_name, target_name, target_column = self._edge_record_identity(record)
            by_target_model[target_name].append(record)
            by_source_resource[source_name].append(record)
            by_target_column.setdefault((target_name, target_column), record)
        object.__setattr__(
            self,
            "_edge_records_by_target_model",
            {key: tuple(value) for key, value in by_target_model.items()},
        )
        object.__setattr__(
            self,
            "_edge_records_by_source_resource",
            {key: tuple(value) for key, value in by_source_resource.items()},
        )
        object.__setattr__(self, "_edge_record_by_target_column", by_target_column)
        object.__setattr__(
            self,
            "_edge_counts_by_target_model",
            {key: len(value) for key, value in self._edge_records_by_target_model.items()},
        )
        object.__setattr__(self, "_indexes_initialized", True)

    def _ensure_indexes(self) -> None:
        if self._indexes_initialized:
            return
        object.__setattr__(self, "_edge_records", self._build_fast_edge_records())
        self._initialize_indexes()

    def _materialize_edge(self, record: object) -> ColumnLineageEdge:
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
        ) = self._edge_record_values(record)
        key: tuple[
            str,
            str,
            str,
            str,
            str,
            ColumnTransformKind,
            ColumnLineageConfidence,
        ] = (
            str(resource_type),
            resource_name,
            source_column,
            target_model,
            target_column,
            transform_kind,
            confidence,
        )
        cached: ColumnLineageEdge | None = self._edge_cache.get(key)
        if cached is not None:
            return cached
        edge: ColumnLineageEdge = ColumnLineageEdge(
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

    @staticmethod
    def _edge_record_identity(record: object) -> tuple[str, str, str]:
        if isinstance(record, ColumnLineageEdge):
            return (
                record.source.resource_name,
                record.target.resource_name,
                record.target.column_name,
            )
        _, resource_name, _, target_model, target_column, _, _ = (
            ProjectColumnLineage._edge_record_values(record)
        )
        return resource_name, target_model, target_column

    @staticmethod
    def _edge_record_values(
        record: object,
    ) -> tuple[
        CompiledResourceType | str,
        str,
        str,
        str,
        str,
        ColumnTransformKind,
        ColumnLineageConfidence,
    ]:
        if isinstance(record, tuple) and len(record) == INDEXED_EDGE_RECORD_LENGTH:
            facts, source, target_model, target_column, transform_code, confidence_code = cast(
                tuple[CompactLineageFacts, tuple[int, int, int], str, str, int, int], record
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
            tuple[
                CompiledLineageSourceFact | ColumnLineageSource,
                str,
                str,
                ColumnTransformKind,
                ColumnLineageConfidence,
            ],
            record,
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

    @staticmethod
    def _model_lineage_from_compact_facts(
        *,
        model_name: str,
        columns: Sequence[CompiledLineageColumnFact],
        has_star: bool,
    ) -> ModelColumnLineage:
        lineage_columns: list[ColumnLineage] = []
        for column in columns:
            upstream_columns: list[ColumnLineageSource] = []
            for source in column.upstream_columns:
                upstream_columns.append(
                    ColumnLineageSource(
                        resource_type=source.resource_type,
                        resource_name=source.resource_name,
                        column_name=source.column_name,
                    )
                )
            lineage_columns.append(
                ColumnLineage(
                    output_column=column.output_column,
                    transform_kind=column.transform_kind,
                    expression_sql=None,
                    upstream_columns=tuple(upstream_columns),
                    nullability=InferredNullability.UNKNOWN,
                    confidence=column.confidence,
                )
            )
        return ModelColumnLineage(
            model_name=model_name,
            columns=tuple(lineage_columns),
            has_star=has_star,
        )

    def __repr__(self) -> str:
        return f"ProjectColumnLineage(models={self.models!r}, edges={self.edges!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ProjectColumnLineage):
            return NotImplemented
        return self.models == other.models and self.edges == other.edges
