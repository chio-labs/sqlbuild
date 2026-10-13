"""Column lineage result models."""

from __future__ import annotations

from dataclasses import dataclass

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
