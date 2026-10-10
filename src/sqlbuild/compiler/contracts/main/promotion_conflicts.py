"""Report enforced contracts that the effective table promotion mode cannot validate."""

from __future__ import annotations

from sqlbuild.adapter.contract.types import TablePromotionMode
from sqlbuild.compiler.compile.models import CompiledProject, CompilerDiagnostic
from sqlbuild.compiler.contracts.main._native_promotion_conflicts import (
    native_promotion_conflict_diagnostics,
)


def promotion_conflict_diagnostics(
    *,
    project: CompiledProject,
    adapter_default: TablePromotionMode,
    settings_file: str,
) -> tuple[CompilerDiagnostic, ...]:
    """Return one K011 error per enforced-contract table model under immediate promotion."""

    return native_promotion_conflict_diagnostics(
        project=project, adapter_default=adapter_default, settings_file=settings_file
    )
