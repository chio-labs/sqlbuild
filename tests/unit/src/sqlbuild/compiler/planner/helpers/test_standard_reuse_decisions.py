from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models.core import CompiledRelationDestination
from sqlbuild.compiler.planner.helpers.standard_reuse_decisions import (
    build_standard_reuse_decisions,
)
from sqlbuild.compiler.planner.models import (
    PlannerScope,
    StandardReuseDecisionResults,
    StandardReuseSourceModelSnapshot,
    StandardReuseSourceSnapshot,
)
from sqlbuild.compiler.planner.types import StandardReuseDecisionKind
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    StandardReuseDecisionTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    build_standard_reuse_decision_scope,
    build_standard_reuse_fingerprint,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StandardReuseDecisionTestCase(
            description="classifies standard reuse decisions",
            expected_decisions={
                "candidate": StandardReuseDecisionKind.REUSE_CANDIDATE.value,
                "current": StandardReuseDecisionKind.CURRENT.value,
                "missing_fingerprint": (StandardReuseDecisionKind.SOURCE_FINGERPRINT_MISSING.value),
                "missing_relation": StandardReuseDecisionKind.SOURCE_RELATION_MISSING.value,
                "version_mismatch": StandardReuseDecisionKind.SOURCE_VERSION_MISMATCH.value,
                "ineligible_view": StandardReuseDecisionKind.INELIGIBLE_MATERIALIZATION.value,
                "incremental_candidate": StandardReuseDecisionKind.REUSE_CANDIDATE.value,
                "ineligible_custom": StandardReuseDecisionKind.INELIGIBLE_MATERIALIZATION.value,
                "missing_expected": StandardReuseDecisionKind.SOURCE_VERSION_MISMATCH.value,
                "current_source_missing": StandardReuseDecisionKind.CURRENT.value,
            },
        )
    ],
    ids=["classifies standard reuse decisions"],
)
def test_given_source_snapshot_when_building_standard_reuse_decisions_then_classifies_models(
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
            "ineligible_custom": "expected",
            "current_source_missing": "expected",
        },
        built_fingerprints={
            "current": build_standard_reuse_fingerprint(
                model_name="current",
                version_hash="expected",
            ),
            "current_source_missing": build_standard_reuse_fingerprint(
                model_name="current_source_missing",
                version_hash="expected",
            ),
        },
        source_snapshot=StandardReuseSourceSnapshot(
            target_name="prod",
            fingerprint_database=None,
            fingerprint_schema="prod_schema",
            model_snapshots={
                "candidate": StandardReuseSourceModelSnapshot(
                    model_name="candidate",
                    destination=CompiledRelationDestination(
                        database=None,
                        schema="prod_schema",
                        name="candidate",
                        qualified_name="prod_schema.candidate",
                    ),
                    relation_exists=True,
                    built_version_hash="expected",
                ),
                "current": StandardReuseSourceModelSnapshot(
                    model_name="current",
                    destination=CompiledRelationDestination(
                        database=None,
                        schema="prod_schema",
                        name="current",
                        qualified_name="prod_schema.current",
                    ),
                    relation_exists=True,
                    built_version_hash="expected",
                ),
                "missing_fingerprint": StandardReuseSourceModelSnapshot(
                    model_name="missing_fingerprint",
                    destination=CompiledRelationDestination(
                        database=None,
                        schema="prod_schema",
                        name="missing_fingerprint",
                        qualified_name="prod_schema.missing_fingerprint",
                    ),
                    relation_exists=True,
                    built_version_hash=None,
                ),
                "missing_relation": StandardReuseSourceModelSnapshot(
                    model_name="missing_relation",
                    destination=CompiledRelationDestination(
                        database=None,
                        schema="prod_schema",
                        name="missing_relation",
                        qualified_name="prod_schema.missing_relation",
                    ),
                    relation_exists=False,
                    built_version_hash="expected",
                ),
                "version_mismatch": StandardReuseSourceModelSnapshot(
                    model_name="version_mismatch",
                    destination=CompiledRelationDestination(
                        database=None,
                        schema="prod_schema",
                        name="version_mismatch",
                        qualified_name="prod_schema.version_mismatch",
                    ),
                    relation_exists=True,
                    built_version_hash="old",
                ),
                "ineligible_view": StandardReuseSourceModelSnapshot(
                    model_name="ineligible_view",
                    destination=CompiledRelationDestination(
                        database=None,
                        schema="prod_schema",
                        name="ineligible_view",
                        qualified_name="prod_schema.ineligible_view",
                    ),
                    relation_exists=True,
                    built_version_hash="expected",
                ),
                "incremental_candidate": StandardReuseSourceModelSnapshot(
                    model_name="incremental_candidate",
                    destination=CompiledRelationDestination(
                        database=None,
                        schema="prod_schema",
                        name="incremental_candidate",
                        qualified_name="prod_schema.incremental_candidate",
                    ),
                    relation_exists=True,
                    built_version_hash="expected",
                ),
                "ineligible_custom": StandardReuseSourceModelSnapshot(
                    model_name="ineligible_custom",
                    destination=CompiledRelationDestination(
                        database=None,
                        schema="prod_schema",
                        name="ineligible_custom",
                        qualified_name="prod_schema.ineligible_custom",
                    ),
                    relation_exists=True,
                    built_version_hash="expected",
                ),
                "missing_expected": StandardReuseSourceModelSnapshot(
                    model_name="missing_expected",
                    destination=CompiledRelationDestination(
                        database=None,
                        schema="prod_schema",
                        name="missing_expected",
                        qualified_name="prod_schema.missing_expected",
                    ),
                    relation_exists=True,
                    built_version_hash="expected",
                ),
                "current_source_missing": StandardReuseSourceModelSnapshot(
                    model_name="current_source_missing",
                    destination=CompiledRelationDestination(
                        database=None,
                        schema="prod_schema",
                        name="current_source_missing",
                        qualified_name="prod_schema.current_source_missing",
                    ),
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
            description="classifies only selected models",
            expected_decisions={"candidate": StandardReuseDecisionKind.REUSE_CANDIDATE.value},
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
        source_snapshot=StandardReuseSourceSnapshot(
            target_name="prod",
            fingerprint_database=None,
            fingerprint_schema="prod_schema",
            model_snapshots={
                "candidate": StandardReuseSourceModelSnapshot(
                    model_name="candidate",
                    destination=CompiledRelationDestination(
                        database=None,
                        schema="prod_schema",
                        name="candidate",
                        qualified_name="prod_schema.candidate",
                    ),
                    relation_exists=True,
                    built_version_hash="expected",
                ),
                "current": StandardReuseSourceModelSnapshot(
                    model_name="current",
                    destination=CompiledRelationDestination(
                        database=None,
                        schema="prod_schema",
                        name="current",
                        qualified_name="prod_schema.current",
                    ),
                    relation_exists=True,
                    built_version_hash="expected",
                ),
            },
        ),
    )

    assert {
        model_name: decision.decision for model_name, decision in decisions.models.items()
    } == test_case.expected_decisions
