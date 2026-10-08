"""Natively parsed MODEL header metadata and the authored values it was parsed from."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.spec.contracts.models import SchemaAuditInstance, SchemaColumn, SourceLocation


@dataclass(frozen=True, slots=True)
class NativeHeaderMetadata:
    """One model's header columns and audits; `invalid` means Python must parse them and raise."""

    raw_columns: object | None
    raw_audits: object | None
    column_locations: dict[str, SourceLocation]
    columns: tuple[SchemaColumn, ...]
    audits: tuple[SchemaAuditInstance, ...]
    invalid: bool = False

    def applies_to(
        self,
        *,
        raw_columns: object | None,
        raw_audits: object | None,
        column_locations: dict[str, SourceLocation] | None,
    ) -> bool:
        """Return whether this parse was made from exactly these authored objects."""

        return (
            raw_columns is self.raw_columns
            and raw_audits is self.raw_audits
            and column_locations is self.column_locations
        )


@dataclass(frozen=True, slots=True)
class NativeTemplateExpansion:
    """A natively expanded config value and the environment and context names it read, in order."""

    value: object
    reads: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class NativeTemplateRejection:
    """Python's exact template error for a config value and the names read before it, in order."""

    message: str
    reads: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class TemplateResolutionFlags:
    """How one template expansion treats `CTX:` references."""

    allow_context: bool
    preserve_context_tokens: bool
    preserve_unknown_context: bool
