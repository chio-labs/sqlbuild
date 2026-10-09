"""K011 promotion conflicts found by the native engine, materialised as Python builds them."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject, CompilerDiagnostic
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.contracts._helpers.native_deferrals import record_contract_deferral
from sqlbuild.compiler.contracts.constants import (
    NATIVE_CONTRACTS_UNSUPPORTED_INPUT,
    NATIVE_PROMOTION_DEFERRAL_SITE,
)
from sqlbuild.compiler.planner.types import MaterializationType


def native_promotion_conflicts(
    *, project: CompiledProject, adapter_default: object, settings_file: str
) -> tuple[CompilerDiagnostic, ...] | None:
    """Return `promotion_conflict_diagnostics`'s result, or None where Python must build it."""

    explicit_mode: object = project.settings.table_promotion_mode
    if not isinstance(adapter_default, str) or not isinstance(explicit_mode, str | None):
        record_contract_deferral(
            kind=NATIVE_CONTRACTS_UNSUPPORTED_INPUT, site=NATIVE_PROMOTION_DEFERRAL_SITE
        )
        return None
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
