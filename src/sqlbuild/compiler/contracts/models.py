"""Contract validation result models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.compiler.diagnostics.models import CompilerDiagnostic


@dataclass(frozen=True)
class ContractValidationResult:
    """Diagnostics emitted by model contract validation."""

    diagnostics: tuple[CompilerDiagnostic, ...] = field(default_factory=tuple)

    @property
    def has_errors(self) -> bool:
        """Return whether contract validation found errors."""

        return any(diagnostic.is_error for diagnostic in self.diagnostics)
