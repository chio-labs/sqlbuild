"""Plain-data rows exchanged with the native project assembly."""

from __future__ import annotations

type ReferenceRow = tuple[str, str, str | None]
type SyntaxCheckRow = tuple[str, list[tuple[str, str]]]
type VariableRow = tuple[str, str, str]
type ModelRow = tuple[list[ReferenceRow], list[SyntaxCheckRow]]
type SourceRow = tuple[str, bool, str | None, str | None]
type SeedRow = tuple[str, str | None, str | None]
type AuditRow = tuple[list[ReferenceRow], tuple[str, str] | None]
type TargetRow = tuple[str | None, str | None, str | None]
type DefaultsRow = tuple[str | None, str | None, str | None, str | None]
type ProjectRequestRow = tuple[
    str,
    TargetRow | None,
    DefaultsRow,
    list[VariableRow],
    list[tuple[str, str | None]],
    list[ModelRow],
    list[SourceRow],
    list[SeedRow],
    list[list[ReferenceRow]],
    list[AuditRow],
]
type ObjectKeyRow = tuple[str, str]
type NamespaceRow = tuple[str | None, str | None, str | None, str | None]
type ProjectResourcesRow = tuple[
    list[list[ObjectKeyRow]],
    list[tuple[str | None, str | None] | None],
    list[NamespaceRow],
    list[list[ObjectKeyRow]],
    list[list[ObjectKeyRow]],
    list[tuple[str, str]],
    list[bool],
]
