"""Structured raw source metadata models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.spec.models.schema import SchemaAuditInstance
from sqlbuild.spec.models.types import SourceWriteStrategy


@dataclass(frozen=True)
class IntegrationLoaderConfig:
    """Typed configuration for one declarative integration loader."""

    kind: str
    config: object


@dataclass(frozen=True)
class SourceColumnEntry:
    """One source column entry from sources/*.yml."""

    name: str
    type: str | None = None
    nullable: bool | None = None
    description: str | None = None
    meta: dict[str, object] = field(default_factory=dict)
    audits: tuple[SchemaAuditInstance, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SourceEntry:
    """One source declaration from sources/*.yml."""

    name: str
    database: str | None = None
    schema: str | None = None
    table: str | None = None
    loader: str | None = None
    integration_loader: IntegrationLoaderConfig | None = None
    write_strategy: SourceWriteStrategy | None = None
    load_batch_size: int | None = None
    cursor_column: str | None = None
    unique_key: tuple[str, ...] = field(default_factory=tuple)
    expression: str | None = None
    description: str | None = None
    type_enforcement: bool | None = None
    contract: str | None = None
    meta: dict[str, object] = field(default_factory=dict)
    columns: tuple[SourceColumnEntry, ...] = field(default_factory=tuple)
    audits: tuple[SchemaAuditInstance, ...] = field(default_factory=tuple)
