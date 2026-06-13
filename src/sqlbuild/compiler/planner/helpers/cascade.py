"""Backfill cascade propagation through the dependency graph."""

from __future__ import annotations

import re
from datetime import timedelta

from sqlbuild.compiler.compile.models.core import CompiledModel, CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.helpers.changes.policy import resolve_replay_on_change
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    CascadeCause,
    CascadeResult,
    ChangeDetectionResult,
    FunctionChangeResult,
    PlannerChangeResults,
    PlannerResolvedActions,
    PlannerScope,
    ResolvedModelAction,
)
from sqlbuild.compiler.planner.types import BackfillAction, ChangeKind, PlanReason

_DURATION_PATTERN: re.Pattern[str] = re.compile(r"^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")

_ACTION_RANK: dict[BackfillAction, int] = {
    BackfillAction.FORWARD_ONLY: 0,
    BackfillAction.BOUNDED: 1,
    BackfillAction.FULL: 2,
}


def resolve_cascades(
    *,
    scope: PlannerScope,
    changes: PlannerChangeResults,
) -> PlannerResolvedActions:
    """Resolve effective model actions after upstream cascade propagation."""

    effective_cascades: dict[str, CascadeResult] = {}
    function_name: str
    function_change: FunctionChangeResult
    for function_name, function_change in changes.functions.items():
        if function_change.backfill.action == BackfillAction.FORWARD_ONLY:
            continue
        effective_cascades[function_name] = build_self_cascade(
            function_change.backfill,
            root_cause=function_name,
            root_reason=(
                PlanReason.FUNCTION_CHANGED
                if function_change.reason == PlanReason.QUERY_CHANGED
                else function_change.reason
            ),
        )

    model_cursor_types: dict[str, str | None] = {}
    resolved: dict[str, ResolvedModelAction] = {}
    key: CompiledObjectKey
    for key in scope.execution_order:
        if key not in scope.selected_keys or key.resource_type != CompiledResourceType.MODEL:
            continue
        model: CompiledModel | None = scope.models_by_name.get(key.name)
        change: ChangeDetectionResult | None = changes.models.get(key.name)
        if model is None or change is None:
            continue
        cursor_type: str | None = _get_config_str(model, "cursor_type")
        model_cursor_types[model.name] = cursor_type
        local_policy: str | None = _get_config_str(model, "replay_on_change")
        cascade: CascadeResult | None = resolve_cascade(
            model_name=model.name,
            own_backfill=change.backfill,
            local_backfill=resolve_replay_on_change(replay_on_change=local_policy),
            own_cursor_type=cursor_type,
            upstream_keys=scope.upstream_deps.get(key, ()),
            effective_cascades=effective_cascades,
            model_cursor_types=model_cursor_types,
        )
        if cascade is None:
            resolved[model.name] = ResolvedModelAction(
                change=change,
                backfill=change.backfill,
            )
            effective_cascades[model.name] = build_self_cascade(
                change.backfill,
                root_cause=model.name,
                root_reason=_reason_for_change(change),
            )
            continue
        backfill: BackfillResult = BackfillResult(
            action=cascade.effective_action,
            duration=cascade.effective_duration,
        )
        resolved[model.name] = ResolvedModelAction(
            change=change,
            backfill=backfill,
            cascade=cascade,
        )
        effective_cascades[model.name] = cascade

    return PlannerResolvedActions(models=resolved)


def resolve_cascade(
    *,
    model_name: str,
    own_backfill: BackfillResult,
    local_backfill: BackfillResult,
    own_cursor_type: str | None,
    upstream_keys: tuple[CompiledObjectKey, ...],
    effective_cascades: dict[str, CascadeResult],
    model_cursor_types: dict[str, str | None],
) -> CascadeResult | None:
    """Resolve the effective backfill for a model after upstream cascade propagation.

    Returns None if no upstream changes the model's effective propagated
    backfill. Returns a CascadeResult with the effective window, all
    contributing upstream causes, and the nominated root decider.
    """

    candidates: list[CascadeCause] = _gather_cascade_candidates(
        own_cursor_type=own_cursor_type,
        upstream_keys=upstream_keys,
        effective_cascades=effective_cascades,
        model_cursor_types=model_cursor_types,
    )

    if not candidates:
        return None

    winning: CascadeCause | None = _pick_winner(candidates=candidates)
    if winning is None:
        return None

    resolved_backfill: BackfillResult = _resolve_effective_backfill(
        own_backfill=own_backfill,
        local_backfill=local_backfill,
        incoming_cascade=winning,
    )
    if _backfills_match(resolved_backfill, own_backfill):
        return None

    return CascadeResult(
        effective_action=resolved_backfill.action,
        effective_duration=resolved_backfill.duration,
        root_cause=winning.root_cause or winning.model_name,
        root_reason=winning.root_reason,
        causes=tuple(candidates),
    )


def build_self_cascade(
    backfill: BackfillResult,
    *,
    root_cause: str | None = None,
    root_reason: PlanReason | None = None,
) -> CascadeResult:
    """Build a CascadeResult representing a model's own backfill for the accumulator."""

    return CascadeResult(
        effective_action=backfill.action,
        effective_duration=backfill.duration,
        root_cause=root_cause,
        root_reason=root_reason,
        causes=(),
    )


def _gather_cascade_candidates(
    *,
    own_cursor_type: str | None,
    upstream_keys: tuple[CompiledObjectKey, ...],
    effective_cascades: dict[str, CascadeResult],
    model_cursor_types: dict[str, str | None],
) -> list[CascadeCause]:
    """Gather upstream effective backfills that can cascade to this model."""

    candidates: list[CascadeCause] = []
    key: CompiledObjectKey
    for key in upstream_keys:
        if key.resource_type not in (
            CompiledResourceType.MODEL,
            CompiledResourceType.UDF,
            CompiledResourceType.TABLE_FN,
        ):
            continue
        upstream_cascade: CascadeResult | None = effective_cascades.get(key.name)
        if upstream_cascade is None:
            continue
        if upstream_cascade.effective_action == BackfillAction.FORWARD_ONLY:
            continue

        if key.resource_type in {CompiledResourceType.UDF, CompiledResourceType.TABLE_FN}:
            candidates.append(
                CascadeCause(
                    model_name=key.name,
                    effective_action=upstream_cascade.effective_action,
                    effective_duration=upstream_cascade.effective_duration,
                    root_cause=upstream_cascade.root_cause or key.name,
                    root_reason=upstream_cascade.root_reason,
                )
            )
            continue

        upstream_cursor_type: str | None = model_cursor_types.get(key.name)
        same_cursor_type: bool = (
            own_cursor_type is not None
            and upstream_cursor_type is not None
            and own_cursor_type == upstream_cursor_type
        )

        if upstream_cascade.effective_action == BackfillAction.FULL:
            candidates.append(
                CascadeCause(
                    model_name=key.name,
                    effective_action=upstream_cascade.effective_action,
                    effective_duration=upstream_cascade.effective_duration,
                    root_cause=upstream_cascade.root_cause or key.name,
                    root_reason=upstream_cascade.root_reason,
                )
            )
        elif same_cursor_type:
            candidates.append(
                CascadeCause(
                    model_name=key.name,
                    effective_action=upstream_cascade.effective_action,
                    effective_duration=upstream_cascade.effective_duration,
                    root_cause=upstream_cascade.root_cause or key.name,
                    root_reason=upstream_cascade.root_reason,
                )
            )

    return candidates


def _pick_winner(
    *,
    candidates: list[CascadeCause],
) -> CascadeCause | None:
    """Pick the strongest incoming candidate.

    Among tied candidates, pick alphabetically by model name.
    """

    best: CascadeCause | None = None
    best_rank: tuple[int, int] | None = None

    candidate: CascadeCause
    for candidate in candidates:
        candidate_rank: tuple[int, int] = _backfill_rank(
            candidate.effective_action, candidate.effective_duration
        )
        if best_rank is None or candidate_rank > best_rank:
            best = candidate
            best_rank = candidate_rank
        elif candidate_rank == best_rank and best is not None:
            if candidate.model_name < best.model_name:
                best = candidate

    return best


def _resolve_effective_backfill(
    *,
    own_backfill: BackfillResult,
    local_backfill: BackfillResult,
    incoming_cascade: CascadeCause,
) -> BackfillResult:
    """Resolve the model's outgoing pressure from local and incoming state."""

    if own_backfill.action != BackfillAction.FORWARD_ONLY:
        return own_backfill
    if local_backfill.action != BackfillAction.FORWARD_ONLY:
        return local_backfill
    return BackfillResult(
        action=incoming_cascade.effective_action,
        duration=incoming_cascade.effective_duration,
    )


def _backfills_match(a: BackfillResult, b: BackfillResult) -> bool:
    """Return True when two backfill results resolve identically."""

    return a.action == b.action and a.duration == b.duration


def _backfill_rank(action: BackfillAction, duration: str | None) -> tuple[int, int]:
    """Produce a comparable rank tuple for a backfill action.

    Returns (action_rank, duration_seconds) where action_rank orders
    FORWARD_ONLY < BOUNDED < FULL, and duration_seconds orders bounded
    durations by total size.
    """

    action_rank: int = _ACTION_RANK[action]
    duration_seconds: int = 0
    if action == BackfillAction.BOUNDED and duration is not None:
        td: timedelta | None = _parse_duration(duration)
        if td is not None:
            duration_seconds = int(td.total_seconds())
    return (action_rank, duration_seconds)


def _get_config_str(model: CompiledModel, key: str) -> str | None:
    value: object | None = model.config.values.get(key)
    return value if isinstance(value, str) else None


def _reason_for_change(change: ChangeDetectionResult) -> PlanReason:
    if change.change_kind == ChangeKind.QUERY_CHANGED:
        return PlanReason.QUERY_CHANGED
    if change.change_kind == ChangeKind.CONFIG_CHANGED:
        return PlanReason.CONFIG_CHANGED
    if change.change_kind == ChangeKind.SCHEMA_CHANGED:
        return PlanReason.SCHEMA_CHANGED
    if change.change_kind == ChangeKind.FIRST_RUN:
        return PlanReason.FIRST_RUN
    return PlanReason.NO_CHANGE


def _parse_duration(duration: str) -> timedelta | None:
    """Parse a duration string like '1d', '6h', '30m', '15s' into a timedelta."""

    match: re.Match[str] | None = _DURATION_PATTERN.match(duration)
    if match is None:
        return None
    days: int = int(match.group(1) or 0)
    hours: int = int(match.group(2) or 0)
    minutes: int = int(match.group(3) or 0)
    seconds: int = int(match.group(4) or 0)
    if days == 0 and hours == 0 and minutes == 0 and seconds == 0:
        return None
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
