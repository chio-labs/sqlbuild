"""Compile-time conflicts between enforced contracts and immediate table promotion."""

from __future__ import annotations

from sqlbuild.adapter.contract.types import TablePromotionMode
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject, CompilerDiagnostic
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.discovery.constants import (
    SETTINGS_SECTION,
    STAGED_PROMOTION_MODE,
    TABLE_PROMOTION_MODE_SETTING_KEY,
)
from sqlbuild.compiler.planner.types import ContractPolicy, IncrementalMode, MaterializationType
from sqlbuild.errors.setting_help.main.join_helps import join_helps
from sqlbuild.errors.setting_help.main.setting_help import setting_help
from sqlbuild.errors.setting_help.main.setting_note import setting_note
from sqlbuild.errors.setting_help.main.snippet_help import snippet_help

_PROMOTION_CONFLICT_CODE: str = "K011"
_STAGED_LIFECYCLE_MATERIALIZATIONS: frozenset[MaterializationType] = frozenset(
    {MaterializationType.TABLE, MaterializationType.INCREMENTAL}
)


def promotion_conflict_diagnostics_impl(
    *,
    project: CompiledProject,
    adapter_default: TablePromotionMode,
    settings_file: str,
) -> tuple[CompilerDiagnostic, ...]:
    """Report each enforced-contract table model when promotion is immediate."""

    explicit_mode: str | None = project.settings.table_promotion_mode
    effective_mode: str = explicit_mode if explicit_mode is not None else adapter_default
    if effective_mode != TablePromotionMode.IMMEDIATE:
        return ()
    help_text: str = _conflict_help(
        explicit=explicit_mode is not None,
        adapter_default=adapter_default,
        settings_file=settings_file,
    )
    return tuple(
        CompilerDiagnostic(
            phase=DiagnosticPhase.CONTRACT,
            severity=DiagnosticSeverity.ERROR,
            code=_PROMOTION_CONFLICT_CODE,
            message=(
                f"model '{model.name}': contract enforced requires staged table promotion; "
                "immediate table promotion cannot validate runtime output before target mutation"
            ),
            resource_type=CompiledResourceType.MODEL,
            resource_name=model.name,
            path=model.relative_path,
            help=help_text,
        )
        for model in project.models
        if _uses_staged_table_lifecycle(model)
    )


def _uses_staged_table_lifecycle(model: CompiledModel) -> bool:
    values: dict[str, object] = model.config.values
    if values.get("contract") != ContractPolicy.ENFORCED:
        return False
    materialized: object = values.get("materialized", MaterializationType.TABLE)
    return (
        materialized in _STAGED_LIFECYCLE_MATERIALIZATIONS
        and values.get("incremental_mode") != IncrementalMode.MICROBATCH
    )


def _conflict_help(
    *, explicit: bool, adapter_default: TablePromotionMode, settings_file: str
) -> str:
    current: str = (
        setting_note(
            file_name=settings_file,
            section=SETTINGS_SECTION,
            key=TABLE_PROMOTION_MODE_SETTING_KEY,
            value=TablePromotionMode.IMMEDIATE.value,
            explicit=explicit,
        )
        + "; enforced contracts are validated in a staging table before promotion"
    )
    staged_fix: str = (
        snippet_help(
            purpose="remove that line to use the default staged promotion",
            target=f"or set this in {settings_file}",
            lines=(
                f"[{SETTINGS_SECTION}]",
                f'{TABLE_PROMOTION_MODE_SETTING_KEY} = "{STAGED_PROMOTION_MODE}"',
            ),
        )
        if explicit and adapter_default == TablePromotionMode.STAGED
        else setting_help(
            purpose="to validate enforced contracts before promotion",
            file_name=settings_file,
            section=SETTINGS_SECTION,
            key=TABLE_PROMOTION_MODE_SETTING_KEY,
            value=STAGED_PROMOTION_MODE,
        )
    )
    return join_helps(
        current,
        staged_fix,
        "or remove the model's enforced contract: `contract enforced` in its MODEL header, or "
        '`contract = "enforced"` in the [defaults] or [path_defaults] entry that applies to it',
    )
