from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.helpers.reuse.standard_reuse_decisions import (
    build_standard_reuse_decisions,
)
from sqlbuild.compiler.planner.models import (
    ModelCursorSnapshot,
    PlannerScope,
    StandardReuseDecisionResults,
    StandardReuseFromTargetSnapshot,
)
from sqlbuild.compiler.planner.types import StandardReuseDecisionKind
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    StandardSourceFreshnessPlanningResult,
    StandardSourceFreshnessPropagationResult,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    StandardReuseDecisionTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    build_standard_reuse_decision_scope,
    build_standard_reuse_fingerprint,
    build_standard_reuse_origin_snapshot,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StandardReuseDecisionTestCase(
            description="classifies standard reuse decisions",
            expected_decisions={
                "candidate": StandardReuseDecisionKind.REUSE_ELIGIBLE.value,
                "current": StandardReuseDecisionKind.CURRENT.value,
                "missing_fingerprint": (
                    StandardReuseDecisionKind.REUSE_ORIGIN_FINGERPRINT_MISSING.value
                ),
                "missing_relation": StandardReuseDecisionKind.REUSE_ORIGIN_RELATION_MISSING.value,
                "version_mismatch": StandardReuseDecisionKind.REUSE_ORIGIN_VERSION_MISMATCH.value,
                "ineligible_view": StandardReuseDecisionKind.INELIGIBLE_MATERIALIZATION.value,
                "incremental_candidate": StandardReuseDecisionKind.REUSE_ELIGIBLE.value,
                "snapshot_candidate": StandardReuseDecisionKind.REUSE_ELIGIBLE.value,
                "ineligible_custom": StandardReuseDecisionKind.INELIGIBLE_MATERIALIZATION.value,
                "missing_expected": StandardReuseDecisionKind.REUSE_ORIGIN_VERSION_MISMATCH.value,
                "current_reuse_from_missing": StandardReuseDecisionKind.CURRENT.value,
            },
        )
    ],
    ids=["classifies standard reuse decisions"],
)
def test_given_reuse_from_snapshot_when_building_standard_reuse_decisions_then_classifies_models(
    test_case: StandardReuseDecisionTestCase,
) -> None:
    scope: PlannerScope = build_standard_reuse_decision_scope()

    decisions: StandardReuseDecisionResults = build_standard_reuse_decisions(
        scope=scope,
        expected_version_hashes={
            "candidate": "expected",
            "current": "expected",
            "missing_fingerprint": "expected",
            "missing_relation": "expected",
            "version_mismatch": "expected",
            "ineligible_view": "expected",
            "incremental_candidate": "expected",
            "snapshot_candidate": "expected",
            "ineligible_custom": "expected",
            "current_reuse_from_missing": "expected",
        },
        built_fingerprints={
            "current": build_standard_reuse_fingerprint(
                model_name="current",
                version_hash="expected",
            ),
            "current_reuse_from_missing": build_standard_reuse_fingerprint(
                model_name="current_reuse_from_missing",
                version_hash="expected",
            ),
        },
        destination_relation_names=frozenset({"current", "current_reuse_from_missing"}),
        reuse_from_snapshot=StandardReuseFromTargetSnapshot(
            reuse_from_target_name="prod",
            model_snapshots={
                "candidate": build_standard_reuse_origin_snapshot(model_name="candidate"),
                "current": build_standard_reuse_origin_snapshot(model_name="current"),
                "missing_fingerprint": build_standard_reuse_origin_snapshot(
                    model_name="missing_fingerprint",
                    built_version_hash=None,
                ),
                "missing_relation": build_standard_reuse_origin_snapshot(
                    model_name="missing_relation",
                    relation_exists=False,
                ),
                "version_mismatch": build_standard_reuse_origin_snapshot(
                    model_name="version_mismatch",
                    built_version_hash="old",
                ),
                "ineligible_view": build_standard_reuse_origin_snapshot(
                    model_name="ineligible_view"
                ),
                "incremental_candidate": build_standard_reuse_origin_snapshot(
                    model_name="incremental_candidate"
                ),
                "snapshot_candidate": build_standard_reuse_origin_snapshot(
                    model_name="snapshot_candidate"
                ),
                "ineligible_custom": build_standard_reuse_origin_snapshot(
                    model_name="ineligible_custom"
                ),
                "missing_expected": build_standard_reuse_origin_snapshot(
                    model_name="missing_expected"
                ),
                "current_reuse_from_missing": build_standard_reuse_origin_snapshot(
                    model_name="current_reuse_from_missing",
                    relation_exists=False,
                    built_version_hash=None,
                ),
            },
        ),
    )

    assert {
        model_name: decision.decision for model_name, decision in decisions.models.items()
    } == test_case.expected_decisions


@pytest.mark.parametrize(
    "test_case",
    [
        StandardReuseDecisionTestCase(
            description="reuse origin version mismatch blocks reuse",
            expected_decisions={
                "version_mismatch": StandardReuseDecisionKind.REUSE_ORIGIN_VERSION_MISMATCH.value,
            },
        )
    ],
    ids=["reuse origin version mismatch blocks reuse"],
)
def test_given_origin_version_differs_then_model_is_not_reused(
    test_case: StandardReuseDecisionTestCase,
) -> None:
    decisions: StandardReuseDecisionResults = build_standard_reuse_decisions(
        scope=build_standard_reuse_decision_scope(
            selected_model_names=frozenset({"version_mismatch"})
        ),
        expected_version_hashes={"version_mismatch": "expected"},
        built_fingerprints={},
        reuse_from_snapshot=StandardReuseFromTargetSnapshot(
            reuse_from_target_name="prod",
            model_snapshots={
                "version_mismatch": build_standard_reuse_origin_snapshot(
                    model_name="version_mismatch",
                    built_version_hash="old",
                ),
            },
        ),
    )

    assert {
        model_name: decision.decision for model_name, decision in decisions.models.items()
    } == test_case.expected_decisions


@pytest.mark.parametrize(
    "test_case",
    [
        StandardReuseDecisionTestCase(
            description="classifies only selected models",
            expected_decisions={"candidate": StandardReuseDecisionKind.REUSE_ELIGIBLE.value},
        )
    ],
    ids=["classifies only selected models"],
)
def test_given_scoped_models_when_building_standard_reuse_decisions_then_classifies_only_selected(
    test_case: StandardReuseDecisionTestCase,
) -> None:
    decisions: StandardReuseDecisionResults = build_standard_reuse_decisions(
        scope=build_standard_reuse_decision_scope(selected_model_names=frozenset({"candidate"})),
        expected_version_hashes={"candidate": "expected", "current": "expected"},
        built_fingerprints={},
        reuse_from_snapshot=StandardReuseFromTargetSnapshot(
            reuse_from_target_name="prod",
            model_snapshots={
                "candidate": build_standard_reuse_origin_snapshot(model_name="candidate"),
                "current": build_standard_reuse_origin_snapshot(model_name="current"),
            },
        ),
    )

    assert {
        model_name: decision.decision for model_name, decision in decisions.models.items()
    } == test_case.expected_decisions


@pytest.mark.parametrize(
    "test_case",
    [
        StandardReuseDecisionTestCase(
            description="downgrades table reuse when source freshness is stale",
            expected_decisions={
                "candidate": StandardReuseDecisionKind.REUSE_FROM_SOURCE_FRESHNESS_STALE.value,
                "incremental_candidate": StandardReuseDecisionKind.REUSE_ELIGIBLE.value,
            },
        )
    ],
    ids=["downgrades table reuse when source freshness is stale"],
)
def test_given_stale_source_freshness_when_building_standard_reuse_decisions_then_table_builds(
    test_case: StandardReuseDecisionTestCase,
) -> None:
    stale_identity: SourceFreshnessIdentity = SourceFreshnessIdentity(
        source_name="raw_orders",
        target_database=None,
        target_schema="raw",
        target_name="orders",
    )

    decisions: StandardReuseDecisionResults = build_standard_reuse_decisions(
        scope=build_standard_reuse_decision_scope(
            selected_model_names=frozenset({"candidate", "incremental_candidate"})
        ),
        expected_version_hashes={
            "candidate": "expected",
            "incremental_candidate": "expected",
        },
        built_fingerprints={},
        reuse_from_snapshot=StandardReuseFromTargetSnapshot(
            reuse_from_target_name="prod",
            model_snapshots={
                "candidate": build_standard_reuse_origin_snapshot(model_name="candidate"),
                "incremental_candidate": build_standard_reuse_origin_snapshot(
                    model_name="incremental_candidate"
                ),
            },
        ),
        reuse_from_source_freshness=StandardSourceFreshnessPlanningResult(
            changed_identities=frozenset({stale_identity}),
            propagation=StandardSourceFreshnessPropagationResult(
                changed_source_model_names={
                    stale_identity: frozenset({"candidate", "incremental_candidate"})
                },
                stale_model_names=frozenset({"candidate", "incremental_candidate"}),
            ),
        ),
    )

    assert {
        model_name: decision.decision for model_name, decision in decisions.models.items()
    } == test_case.expected_decisions
    assert decisions.models["candidate"].reuse_from_source_freshness_current is False
    assert decisions.models["incremental_candidate"].reuse_from_source_freshness_current is False


@pytest.mark.parametrize(
    "test_case",
    [
        StandardReuseDecisionTestCase(
            description="keeps current incremental when destination cursor is numerically ahead",
            expected_decisions={
                "incremental_candidate": StandardReuseDecisionKind.CURRENT.value,
            },
        )
    ],
    ids=["keeps current incremental when destination cursor is numerically ahead"],
)
def test_given_destination_cursor_ahead_when_planning_incremental_reuse_then_stays_current(
    test_case: StandardReuseDecisionTestCase,
) -> None:
    decisions: StandardReuseDecisionResults = build_standard_reuse_decisions(
        scope=build_standard_reuse_decision_scope(
            selected_model_names=frozenset({"incremental_candidate"})
        ),
        expected_version_hashes={"incremental_candidate": "expected"},
        built_fingerprints={
            "incremental_candidate": build_standard_reuse_fingerprint(
                model_name="incremental_candidate",
                version_hash="expected",
            )
        },
        cursor_snapshots={
            "incremental_candidate": ModelCursorSnapshot(
                target_max="10",
                upstream_mins=(),
                upstream_maxes=(),
            )
        },
        destination_relation_names=frozenset({"incremental_candidate"}),
        reuse_from_snapshot=StandardReuseFromTargetSnapshot(
            reuse_from_target_name="prod",
            model_snapshots={
                "incremental_candidate": build_standard_reuse_origin_snapshot(
                    model_name="incremental_candidate",
                    reuse_origin_cursor_max="9",
                ),
            },
        ),
    )

    assert {
        model_name: decision.decision for model_name, decision in decisions.models.items()
    } == test_case.expected_decisions
