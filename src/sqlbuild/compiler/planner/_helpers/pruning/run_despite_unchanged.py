"""Changes-only run_despite_unchanged planning helpers."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlbuild.compiler.compile.models import CompiledModel, CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.constants import (
    RUN_DESPITE_UNCHANGED_HOUR_SUFFIX,
    RUN_DESPITE_UNCHANGED_MINUTE_SUFFIX,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.planning.model_downstream_closure import (
    build_downstream_model_names,
)
from sqlbuild.compiler.planner.models import (
    PlannerScope,
    RunDespiteUnchangedDecision,
    RunDespiteUnchangedPlanningResult,
)
from sqlbuild.compiler.planner.types import MaterializationType, RunDespiteUnchangedMode
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessRecord,
    StandardSourceFreshnessPlanningResult,
)
from sqlbuild.spec.contracts.types import SourceFreshnessValueKind

_DURATION_PATTERN: re.Pattern[str] = re.compile(r"^([1-9][0-9]*)([mhd])$")


def build_run_despite_unchanged_planning_result(
    *,
    scope: PlannerScope,
    source_freshness: StandardSourceFreshnessPlanningResult,
    already_stale_model_names: frozenset[str],
    now: datetime,
) -> RunDespiteUnchangedPlanningResult:
    """Return configured table roots that should run despite unchanged inputs."""

    decisions: dict[str, RunDespiteUnchangedDecision] = {}
    downstream_root_causes: dict[str, str] = {}
    stale_model_names: set[str] = set()
    key: CompiledObjectKey
    for key in scope.selected_keys:
        if key.resource_type != CompiledResourceType.MODEL:
            continue
        model: CompiledModel | None = scope.models_by_name.get(key.name)
        if model is None:
            continue
        raw_value: object | None = model.config.values.get("run_despite_unchanged")
        if raw_value is None:
            continue
        _validate_supported_model(model=model, raw_value=raw_value)
        if model.name in already_stale_model_names:
            _validate_duration_prerequisites_if_needed(
                model=model,
                scope=scope,
                source_freshness=source_freshness,
                now=now,
                raw_value=raw_value,
            )
        decision: RunDespiteUnchangedDecision | None = _decision_for_model(
            model=model,
            scope=scope,
            source_freshness=source_freshness,
            now=now,
            raw_value=raw_value,
        )
        if decision is None:
            continue
        decisions[model.name] = decision
        downstream_names: frozenset[str] = build_downstream_model_names(
            start_keys=(model.key,),
            downstream_deps=scope.downstream_deps,
        )
        stale_model_names.update(downstream_names)
        downstream_name: str
        for downstream_name in sorted(downstream_names - {model.name}):
            downstream_root_causes.setdefault(downstream_name, model.name)

    return RunDespiteUnchangedPlanningResult(
        root_model_names=frozenset(decisions),
        stale_model_names=frozenset(stale_model_names),
        decisions=decisions,
        downstream_root_causes=downstream_root_causes,
    )


def _validate_supported_model(*, model: CompiledModel, raw_value: object) -> None:
    if not isinstance(raw_value, str):
        raise PlannerInputError(
            f"model '{model.name}' run_despite_unchanged must be 'always' or a positive "
            "duration like 30d, 12h, or 90m"
        )
    materialized: object | None = model.config.values.get("materialized")
    if materialized != MaterializationType.TABLE:
        raise PlannerInputError(
            f"model '{model.name}' has run_despite_unchanged, but only table "
            "materializations support it"
        )


def _validate_duration_prerequisites_if_needed(
    *,
    model: CompiledModel,
    scope: PlannerScope,
    source_freshness: StandardSourceFreshnessPlanningResult,
    now: datetime,
    raw_value: object,
) -> None:
    value: str = str(raw_value).strip().lower()
    if value == RunDespiteUnchangedMode.ALWAYS.value:
        return
    _decision_for_model(
        model=model,
        scope=scope,
        source_freshness=source_freshness,
        now=now,
        raw_value=raw_value,
    )


def _decision_for_model(
    *,
    model: CompiledModel,
    scope: PlannerScope,
    source_freshness: StandardSourceFreshnessPlanningResult,
    now: datetime,
    raw_value: object,
) -> RunDespiteUnchangedDecision | None:
    value: str = str(raw_value).strip().lower()
    if value == RunDespiteUnchangedMode.ALWAYS.value:
        return RunDespiteUnchangedDecision(
            model_name=model.name,
            mode=RunDespiteUnchangedMode.ALWAYS,
        )

    duration: timedelta = _parse_duration(model_name=model.name, value=value)
    records: tuple[SourceFreshnessRecord, ...] = _upstream_source_records(
        model=model,
        scope=scope,
        source_freshness=source_freshness,
    )
    if not records:
        raise PlannerInputError(
            f"model '{model.name}' has run_despite_unchanged = {value}, but SQLBuild "
            "cannot determine upstream source freshness age. Configure timestamp source "
            "freshness for at least one upstream source, use run_despite_unchanged always, "
            "or remove the setting."
        )

    newest_record: SourceFreshnessRecord = max(
        records,
        key=lambda record: _timestamp_data_version(
            model_name=model.name,
            record=record,
        ),
    )
    newest_timestamp: datetime = _timestamp_data_version(
        model_name=model.name,
        record=newest_record,
    )
    age_seconds: int = max(0, int((_normalize_now(now) - newest_timestamp).total_seconds()))
    if timedelta(seconds=age_seconds) > duration:
        return None
    return RunDespiteUnchangedDecision(
        model_name=model.name,
        mode=RunDespiteUnchangedMode.DURATION,
        duration=value,
        newest_source_name=newest_record.source_name,
        newest_source_data_age_seconds=age_seconds,
    )


def _parse_duration(*, model_name: str, value: str) -> timedelta:
    match: re.Match[str] | None = _DURATION_PATTERN.match(value)
    if match is None:
        raise PlannerInputError(
            f"model '{model_name}' run_despite_unchanged must be 'always' or a positive "
            "duration like 30d, 12h, or 90m"
        )
    amount: int = int(match.group(1))
    unit: str = match.group(2)
    if unit == RUN_DESPITE_UNCHANGED_MINUTE_SUFFIX:
        return timedelta(minutes=amount)
    if unit == RUN_DESPITE_UNCHANGED_HOUR_SUFFIX:
        return timedelta(hours=amount)
    return timedelta(days=amount)


def _upstream_source_records(
    *,
    model: CompiledModel,
    scope: PlannerScope,
    source_freshness: StandardSourceFreshnessPlanningResult,
) -> tuple[SourceFreshnessRecord, ...]:
    upstream_source_names: frozenset[str] = _upstream_source_names(
        start_key=model.key,
        upstream_deps=scope.upstream_deps,
    )
    records: list[SourceFreshnessRecord] = []
    record: SourceFreshnessRecord
    for record in source_freshness.observed_records:
        if record.source_name not in upstream_source_names:
            continue
        if record.value_kind != SourceFreshnessValueKind.TIMESTAMP.value:
            raise PlannerInputError(
                f"model '{model.name}' has run_despite_unchanged = "
                f"{model.config.values.get('run_despite_unchanged')}, but upstream source "
                f"'{record.source_name}' uses {record.value_kind} freshness. Duration mode "
                "requires timestamp source freshness; use run_despite_unchanged always or "
                "configure timestamp source freshness."
            )
        records.append(record)
    return tuple(records)


def _upstream_source_names(
    *,
    start_key: CompiledObjectKey,
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[str]:
    result: set[str] = set()
    visited: set[CompiledObjectKey] = set()
    stack: list[CompiledObjectKey] = [start_key]
    while stack:
        current: CompiledObjectKey = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        if current.resource_type == CompiledResourceType.SOURCE:
            result.add(current.name)
            continue
        neighbor: CompiledObjectKey
        for neighbor in upstream_deps.get(current, ()):
            stack.append(neighbor)
    return frozenset(result)


def _timestamp_data_version(*, model_name: str, record: SourceFreshnessRecord) -> datetime:
    if record.data_version is None:
        raise PlannerInputError(
            f"model '{model_name}' cannot determine source freshness age because source "
            f"'{record.source_name}' has no data_version"
        )
    try:
        timestamp: datetime = datetime.fromisoformat(record.data_version)
    except ValueError as exc:
        raise PlannerInputError(
            f"model '{model_name}' cannot determine source freshness age because source "
            f"'{record.source_name}' has invalid timestamp data_version "
            f"'{record.data_version}'"
        ) from exc
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def _normalize_now(now: datetime) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)
