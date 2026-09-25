"""Contract validation result models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.compiler.compile.models import CompilerDiagnostic


@dataclass(frozen=True)
class ContractValidationResult:
    """Diagnostics emitted by model contract validation."""

    diagnostics: tuple[CompilerDiagnostic, ...] = field(default_factory=tuple)
