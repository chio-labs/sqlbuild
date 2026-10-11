"""K011 promotion conflicts found by the native engine, materialised as Python builds them."""

from __future__ import annotations

from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.adapter.contract.types import TablePromotionMode
from sqlbuild.compiler.compile.models import CompilerDiagnostic
from sqlbuild.compiler.compile.types import (
    CompiledProjectView,
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.compiled_project.main.compiled_project_facts import compiled_project_facts


def native_promotion_conflicts(
    *, project: CompiledProjectView, adapter_default: TablePromotionMode, settings_file: str
) -> tuple[CompilerDiagnostic, ...]:
    """Return one K011 error per enforced-contract table model under immediate promotion."""

    explicit_mode: str | None = project.settings.table_promotion_mode
    conflicts: list[tuple[str, str, str, str, str]] = _native.project_promotion_conflicts(
        (explicit_mode, str(adapter_default), settings_file), compiled_project_facts(project)
    )
    return tuple(
        CompilerDiagnostic(
            phase=DiagnosticPhase.CONTRACT,
            severity=DiagnosticSeverity.ERROR,
            code=code,
            message=message,
            resource_type=CompiledResourceType.MODEL,
            resource_name=name,
            path=Path(relative_path),
            help=help_text,
        )
        for name, relative_path, code, message, help_text in conflicts
    )
