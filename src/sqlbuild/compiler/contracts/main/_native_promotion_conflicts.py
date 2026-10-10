"""Find promotion conflicts natively."""

from __future__ import annotations

from sqlbuild.adapter.contract.types import TablePromotionMode
from sqlbuild.compiler.compile.models import CompiledProject, CompilerDiagnostic
from sqlbuild.compiler.contracts._helpers.native_promotion import native_promotion_conflicts


def native_promotion_conflict_diagnostics(
    *, project: CompiledProject, adapter_default: TablePromotionMode, settings_file: str
) -> tuple[CompilerDiagnostic, ...]:
    """Return the K011 promotion conflicts."""

    return native_promotion_conflicts(
        project=project, adapter_default=adapter_default, settings_file=settings_file
    )
