"""Compiler diagnostic data models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.diagnostics.types import DiagnosticPhase, DiagnosticSeverity


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

    @property
    def is_error(self) -> bool:
        """Return whether this diagnostic should fail the command."""

        return self.severity == DiagnosticSeverity.ERROR
