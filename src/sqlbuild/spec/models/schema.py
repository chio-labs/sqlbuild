"""Structured raw schema.yml metadata models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SchemaAuditInstance:
    """One schema-attached audit instance from schema.yml."""

    definition_name: str
    arguments: dict[str, object] = field(default_factory=dict)
    name: str | None = None
    description: str | None = None
    severity: str | None = None


@dataclass(frozen=True)
class SchemaColumn:
    """One model or seed column entry from schema.yml."""

    name: str
    type: str | None = None
    description: str | None = None
    meta: dict[str, object] = field(default_factory=dict)
    audits: tuple[SchemaAuditInstance, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SchemaModelEntry:
    """One model entry from schema.yml."""

    name: str
    description: str | None = None
    type_enforcement: bool | None = None
    meta: dict[str, object] = field(default_factory=dict)
    columns: tuple[SchemaColumn, ...] = field(default_factory=tuple)
    audits: tuple[SchemaAuditInstance, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SchemaSeedEntry:
    """One seed entry from schema.yml."""

    name: str
    description: str | None = None
    meta: dict[str, object] = field(default_factory=dict)
    columns: tuple[SchemaColumn, ...] = field(default_factory=tuple)
