from __future__ import annotations

import pytest

from scripts.dupscore._helpers.facts import extract_project_facts
from scripts.dupscore._helpers.signal_state_fanin import score_state_fanin
from scripts.dupscore.models import DupscoreConfig, SignalRanking
from tests.unit.scripts.dupscore._helpers.signal_state_fanin._test_types import (
    StateFaninPairTestCase,
    StateFaninSuppressionTestCase,
)

_STATE_CLASS: str = (
    "class StateBackend:\n"
    "    def get_model_refs(self) -> list[str]:\n"
    "        return []\n"
    "\n"
    "    def get_seed_refs(self) -> list[str]:\n"
    "        return []\n"
)
_PLANNER_READER: str = "def plan(backend: object) -> None:\n    backend.get_model_refs()\n    backend.get_seed_refs()\n"
_EXECUTOR_READER: str = "def build(backend: object) -> None:\n    backend.get_model_refs()\n    backend.get_seed_refs()\n"


@pytest.mark.parametrize(
    "test_case",
    [
        StateFaninPairTestCase(
            description="scores two packages independently reading two state methods",
            sources={
                "src/sqlbuild/alpha/state/backend.py": _STATE_CLASS,
                "src/sqlbuild/alpha/planner/plan.py": _PLANNER_READER,
                "src/sqlbuild/alpha/executor/build.py": _EXECUTOR_READER,
            },
            persisted_state_surfaces=("sqlbuild.alpha.state",),
            expected_top_pair=("sqlbuild.alpha.executor", "sqlbuild.alpha.planner"),
            expected_top_score=2.0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_two_reading_packages_when_scoring_fanin_then_scores_pair(
    test_case: StateFaninPairTestCase,
) -> None:
    config: DupscoreConfig = DupscoreConfig(
        persisted_state_surfaces=test_case.persisted_state_surfaces
    )

    ranking: SignalRanking = score_state_fanin(
        facts=extract_project_facts(test_case.sources),
        config=config,
    )

    assert ranking.entries[0].package_pair == test_case.expected_top_pair
    assert ranking.entries[0].score == test_case.expected_top_score


@pytest.mark.parametrize(
    "test_case",
    [
        StateFaninSuppressionTestCase(
            description="returns nothing when no surfaces are configured",
            sources={
                "src/sqlbuild/alpha/state/backend.py": _STATE_CLASS,
                "src/sqlbuild/alpha/planner/plan.py": _PLANNER_READER,
                "src/sqlbuild/alpha/executor/build.py": _EXECUTOR_READER,
            },
            persisted_state_surfaces=(),
            expected_entry_count=0,
        ),
        StateFaninSuppressionTestCase(
            description="ignores reads from a single external package",
            sources={
                "src/sqlbuild/alpha/state/backend.py": _STATE_CLASS,
                "src/sqlbuild/alpha/planner/plan.py": _PLANNER_READER,
            },
            persisted_state_surfaces=("sqlbuild.alpha.state",),
            expected_entry_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_insufficient_readers_when_scoring_fanin_then_returns_no_pairs(
    test_case: StateFaninSuppressionTestCase,
) -> None:
    config: DupscoreConfig = DupscoreConfig(
        persisted_state_surfaces=test_case.persisted_state_surfaces
    )

    ranking: SignalRanking = score_state_fanin(
        facts=extract_project_facts(test_case.sources),
        config=config,
    )

    assert len(ranking.entries) == test_case.expected_entry_count
