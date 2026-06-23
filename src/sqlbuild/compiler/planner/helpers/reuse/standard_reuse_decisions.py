"""Standard target reuse decision helpers."""

from __future__ import annotations

from datetime import datetime

from sqlbuild.compiler.compile.models.core import CompiledModel
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.helpers.output.strategy import get_materialization_type
from sqlbuild.compiler.planner.models import (
    ModelCursorSnapshot,
    PlannerScope,
    StandardReuseDecisionResults,
    StandardReuseFromTargetModelSnapshot,
    StandardReuseFromTargetSnapshot,
    StandardReuseModelDecision,
)
from sqlbuild.compiler.planner.types import (
    CursorType,
    MaterializationType,
    StandardReuseDecisionKind,
)
from sqlbuild.compiler.source_freshness.models import StandardSourceFreshnessPlanningResult

_REUSE_ELIGIBLE_MATERIALIZATIONS: frozenset[MaterializationType] = frozenset(
    {
        MaterializationType.TABLE,
        MaterializationType.INCREMENTAL,
        MaterializationType.SNAPSHOT,
    }
)


def build_standard_reuse_decisions(
    *,
    scope: PlannerScope,
    expected_version_hashes: dict[str, str],
    built_fingerprints: dict[str, Fingerprint],
    reuse_from_snapshot: StandardReuseFromTargetSnapshot,
    cursor_snapshots: dict[str, ModelCursorSnapshot] | None = None,
    reuse_from_source_freshness: StandardSourceFreshnessPlanningResult | None = None,
    custom_prepare_version_materializations: frozenset[str] = frozenset(),
) -> StandardReuseDecisionResults:
    """Classify selected models as reusable or explain why they are not."""

    decisions: dict[str, StandardReuseModelDecision] = {}
    model: CompiledModel
    for model in scope.models_by_name.values():
        if model.key not in scope.selected_keys:
            continue
        reuse_from_model: StandardReuseFromTargetModelSnapshot | None = (
            reuse_from_snapshot.model_snapshots.get(model.name)
        )
        if reuse_from_model is None:
            continue
        expected_version_hash: str | None = expected_version_hashes.get(model.name)
        reuse_origin_built_version_hash: str | None = reuse_from_model.built_version_hash
        reuse_origin_matches_expected: bool = (
            expected_version_hash is not None
            and reuse_origin_built_version_hash is not None
            and reuse_origin_built_version_hash == expected_version_hash
        )
        destination_cursor_max: str | None = _destination_cursor_max(
            model_name=model.name,
            built_fingerprints=built_fingerprints,
            cursor_snapshots=cursor_snapshots,
        )
        decisions[model.name] = StandardReuseModelDecision(
            model_name=model.name,
            decision=_decision_for_model(
                model=model,
                expected_version_hash=expected_version_hash,
                built_fingerprint=built_fingerprints.get(model.name),
                destination_cursor_max=destination_cursor_max,
                reuse_from_model=reuse_from_model,
                reuse_origin_matches_expected=reuse_origin_matches_expected,
                source_freshness_stale=_source_freshness_stale_for_model(
                    model_name=model.name,
                    source_freshness=reuse_from_source_freshness,
                ),
                custom_prepare_version_materializations=custom_prepare_version_materializations,
            ),
            reuse_from_target_name=reuse_from_snapshot.reuse_from_target_name,
            reuse_origin=reuse_from_model.reuse_origin,
            reuse_origin_fingerprint_database=(reuse_from_model.reuse_origin_fingerprint_database),
            reuse_origin_fingerprint_schema=reuse_from_model.reuse_origin_fingerprint_schema,
            reuse_origin_relation_exists=reuse_from_model.relation_exists,
            reuse_origin_built_version_present=reuse_origin_built_version_hash is not None,
            reuse_origin_matches_expected=reuse_origin_matches_expected,
            reuse_from_source_freshness_current=not _source_freshness_stale_for_model(
                model_name=model.name,
                source_freshness=reuse_from_source_freshness,
            ),
            reuse_origin_cursor_max=reuse_from_model.reuse_origin_cursor_max,
            destination_cursor_max=destination_cursor_max,
        )
    return StandardReuseDecisionResults(
        reuse_from_target_name=reuse_from_snapshot.reuse_from_target_name,
        models=decisions,
        hard_copy=reuse_from_snapshot.hard_copy,
    )


def _decision_for_model(
    *,
    model: CompiledModel,
    expected_version_hash: str | None,
    built_fingerprint: Fingerprint | None,
    destination_cursor_max: str | None,
    reuse_from_model: StandardReuseFromTargetModelSnapshot,
    reuse_origin_matches_expected: bool,
    source_freshness_stale: bool,
    custom_prepare_version_materializations: frozenset[str],
) -> str:
    materialization_type: MaterializationType = get_materialization_type(model)
    custom_materialization_name: str | None = _custom_materialization_name(model)
    custom_supports_prepare_version: bool = (
        materialization_type == MaterializationType.CUSTOM
        and custom_materialization_name in custom_prepare_version_materializations
    )
    if (
        expected_version_hash is not None
        and built_fingerprint is not None
        and built_fingerprint.version_hash == expected_version_hash
    ):
        if (
            materialization_type == MaterializationType.INCREMENTAL
            and reuse_origin_matches_expected
            and reuse_from_model.relation_exists
            and _reuse_origin_cursor_ahead(
                reuse_origin_cursor_max=reuse_from_model.reuse_origin_cursor_max,
                destination_cursor_max=destination_cursor_max,
                cursor_type=_get_config_str(model, "cursor_type"),
            )
        ):
            return StandardReuseDecisionKind.REUSE_ELIGIBLE.value
        return StandardReuseDecisionKind.CURRENT.value
    if (
        materialization_type not in _REUSE_ELIGIBLE_MATERIALIZATIONS
        and not custom_supports_prepare_version
    ):
        return StandardReuseDecisionKind.INELIGIBLE_MATERIALIZATION.value
    if reuse_from_model.built_version_hash is None:
        return StandardReuseDecisionKind.REUSE_ORIGIN_FINGERPRINT_MISSING.value
    if not reuse_from_model.relation_exists:
        return StandardReuseDecisionKind.REUSE_ORIGIN_RELATION_MISSING.value
    if not reuse_origin_matches_expected:
        return StandardReuseDecisionKind.REUSE_ORIGIN_VERSION_MISMATCH.value
    if materialization_type == MaterializationType.TABLE and source_freshness_stale:
        return StandardReuseDecisionKind.REUSE_FROM_SOURCE_FRESHNESS_STALE.value
    return StandardReuseDecisionKind.REUSE_ELIGIBLE.value


def _destination_cursor_max(
    *,
    model_name: str,
    built_fingerprints: dict[str, Fingerprint],
    cursor_snapshots: dict[str, ModelCursorSnapshot] | None,
) -> str | None:
    if model_name not in built_fingerprints or cursor_snapshots is None:
        return None
    cursor_snapshot: ModelCursorSnapshot | None = cursor_snapshots.get(model_name)
    return cursor_snapshot.target_max if cursor_snapshot is not None else None


def _reuse_origin_cursor_ahead(
    *,
    reuse_origin_cursor_max: str | None,
    destination_cursor_max: str | None,
    cursor_type: str | None,
) -> bool:
    if reuse_origin_cursor_max is None:
        return False
    if destination_cursor_max is None:
        return True
    if cursor_type == CursorType.INTEGER.value:
        reuse_origin_integer: int | None = _try_parse_integer(reuse_origin_cursor_max)
        destination_integer: int | None = _try_parse_integer(destination_cursor_max)
        if reuse_origin_integer is not None and destination_integer is not None:
            return reuse_origin_integer > destination_integer
    if cursor_type == CursorType.TIMESTAMP.value:
        reuse_origin_timestamp: datetime | None = _try_parse_timestamp(reuse_origin_cursor_max)
        destination_timestamp: datetime | None = _try_parse_timestamp(destination_cursor_max)
        if reuse_origin_timestamp is not None and destination_timestamp is not None:
            return reuse_origin_timestamp > destination_timestamp
    return reuse_origin_cursor_max > destination_cursor_max


def _get_config_str(model: CompiledModel, key: str) -> str | None:
    value: object | None = model.config.values.get(key)
    return value if isinstance(value, str) else None


def _custom_materialization_name(model: CompiledModel) -> str | None:
    value: object | None = model.config.values.get("materialized")
    return value if isinstance(value, str) else None


def _try_parse_integer(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _try_parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _source_freshness_stale_for_model(
    *,
    model_name: str,
    source_freshness: StandardSourceFreshnessPlanningResult | None,
) -> bool:
    if source_freshness is None or source_freshness.propagation is None:
        return False
    return model_name in source_freshness.propagation.stale_model_names
