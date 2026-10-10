"""K011 promotion conflicts found by the native engine, materialised as Python builds them."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.adapter.contract.types import TablePromotionMode
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject, CompilerDiagnostic
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.planner.types import MaterializationType


def native_promotion_conflicts(
    *, project: CompiledProject, adapter_default: TablePromotionMode, settings_file: str
) -> tuple[CompilerDiagnostic, ...]:
    """Return one K011 error per enforced-contract table model under immediate promotion."""

    explicit_mode: str | None = project.settings.table_promotion_mode
    conflicts: list[tuple[int, str, str, str]] = _native.native_promotion_conflicts(
        (
            explicit_mode,
            str(adapter_default),
            settings_file,
            [_model_row(model) for model in project.models],
        )
    )
    return tuple(
        CompilerDiagnostic(
            phase=DiagnosticPhase.CONTRACT,
            severity=DiagnosticSeverity.ERROR,
            code=code,
            message=message,
            resource_type=CompiledResourceType.MODEL,
            resource_name=project.models[index].name,
            path=project.models[index].relative_path,
            help=help_text,
        )
        for index, code, message, help_text in conflicts
    )


def _model_row(model: CompiledModel) -> tuple[str, str | None, str | None, str | None]:
    values: dict[str, object] = model.config.values
    return (
        model.name,
        _text(values.get("contract")),
        _text(values.get("materialized", MaterializationType.TABLE)),
        _text(values.get("incremental_mode")),
    )


def _text(value: object) -> str | None:
    return str.__str__(value) if isinstance(value, str) else None
