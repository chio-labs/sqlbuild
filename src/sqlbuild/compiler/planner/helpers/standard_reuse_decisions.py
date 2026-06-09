"""Standard target reuse decision helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledModel
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.helpers.strategy import get_materialization_type
from sqlbuild.compiler.planner.models import (
    PlannerScope,
    StandardReuseDecisionResults,
    StandardReuseModelDecision,
    StandardReuseSourceModelSnapshot,
    StandardReuseSourceSnapshot,
)
from sqlbuild.compiler.planner.types import MaterializationType, StandardReuseDecisionKind

_REUSE_ELIGIBLE_MATERIALIZATIONS: frozenset[MaterializationType] = frozenset(
    {
        MaterializationType.TABLE,
        MaterializationType.INCREMENTAL,
    }
)


def build_standard_reuse_decisions(
    *,
    scope: PlannerScope,
    expected_version_hashes: dict[str, str],
    built_fingerprints: dict[str, Fingerprint],
    source_snapshot: StandardReuseSourceSnapshot,
) -> StandardReuseDecisionResults:
    """Classify selected models as reusable or explain why they are not."""

    decisions: dict[str, StandardReuseModelDecision] = {}
    model: CompiledModel
    for model in scope.models_by_name.values():
        if model.key not in scope.selected_keys:
            continue
        source_model: StandardReuseSourceModelSnapshot | None = source_snapshot.model_snapshots.get(
            model.name
        )
        if source_model is None:
            continue
        expected_version_hash: str | None = expected_version_hashes.get(model.name)
        source_built_version_hash: str | None = source_model.built_version_hash
        source_matches_expected: bool = (
            expected_version_hash is not None
            and source_built_version_hash is not None
            and source_built_version_hash == expected_version_hash
        )
        decisions[model.name] = StandardReuseModelDecision(
            model_name=model.name,
            decision=_decision_for_model(
                model=model,
                expected_version_hash=expected_version_hash,
                built_fingerprint=built_fingerprints.get(model.name),
                source_model=source_model,
                source_matches_expected=source_matches_expected,
            ),
            source_target_name=source_snapshot.target_name,
            source_relation_exists=source_model.relation_exists,
            source_built_version_present=source_built_version_hash is not None,
            source_matches_expected=source_matches_expected,
        )
    return StandardReuseDecisionResults(
        source_target_name=source_snapshot.target_name,
        models=decisions,
    )


def _decision_for_model(
    *,
    model: CompiledModel,
    expected_version_hash: str | None,
    built_fingerprint: Fingerprint | None,
    source_model: StandardReuseSourceModelSnapshot,
    source_matches_expected: bool,
) -> str:
    if (
        expected_version_hash is not None
        and built_fingerprint is not None
        and built_fingerprint.version_hash == expected_version_hash
    ):
        return StandardReuseDecisionKind.CURRENT.value
    if get_materialization_type(model) not in _REUSE_ELIGIBLE_MATERIALIZATIONS:
        return StandardReuseDecisionKind.INELIGIBLE_MATERIALIZATION.value
    if source_model.built_version_hash is None:
        return StandardReuseDecisionKind.SOURCE_FINGERPRINT_MISSING.value
    if not source_model.relation_exists:
        return StandardReuseDecisionKind.SOURCE_RELATION_MISSING.value
    if not source_matches_expected:
        return StandardReuseDecisionKind.SOURCE_VERSION_MISMATCH.value
    return StandardReuseDecisionKind.REUSE_CANDIDATE.value
