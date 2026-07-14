"""Compiler diagnostic data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.diagnostics.types import DiagnosticPhase, DiagnosticSeverity
from sqlbuild.spec.contracts.models import SourceLocation


@dataclass(frozen=True)
class RelatedLocation:
    """A secondary authored location that adds context to a diagnostic."""

    label: str
    location: SourceLocation
    message: str | None = None


@dataclass(frozen=True)
class CompilerDiagnostic:
    """One project diagnostic produced by compile-time checks."""

    phase: DiagnosticPhase | str
    severity: DiagnosticSeverity | str
    code: str
    message: str
    resource_type: CompiledResourceType | str | None = None
    resource_name: str | None = None
    column_name: str | None = None
    path: Path | None = None
    line: int | None = None
    column: int | None = None
    location: SourceLocation | None = None
    related_locations: tuple[RelatedLocation, ...] = field(default_factory=tuple)
    help: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "phase", DiagnosticPhase(self.phase))
        object.__setattr__(self, "severity", DiagnosticSeverity(self.severity))
        if self.resource_type is not None:
            object.__setattr__(
                self,
                "resource_type",
                CompiledResourceType(self.resource_type),
            )
        if (
            self.location is None
            and self.path is not None
            and self.line is not None
            and self.column is not None
        ):
            object.__setattr__(
                self,
                "location",
                SourceLocation(path=self.path, line=self.line, column=self.column),
            )
        if self.location is not None:
            object.__setattr__(self, "path", self.location.path)
            object.__setattr__(self, "line", self.location.line)
            object.__setattr__(self, "column", self.location.column)

    @property
    def is_error(self) -> bool:
        """Return whether this diagnostic should fail the command."""

        return self.severity == DiagnosticSeverity.ERROR
