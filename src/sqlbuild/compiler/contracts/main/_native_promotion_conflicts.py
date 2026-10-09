"""Find promotion conflicts natively for the preview compiler engine."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledProject, CompilerDiagnostic
from sqlbuild.compiler.contracts._helpers.native_promotion import native_promotion_conflicts


def native_promotion_conflict_diagnostics(
    *, project: CompiledProject, adapter_default: object, settings_file: str
) -> tuple[CompilerDiagnostic, ...] | None:
    """Return the K011 promotion conflicts, or None where Python must find them."""

    return native_promotion_conflicts(
        project=project, adapter_default=adapter_default, settings_file=settings_file
    )
