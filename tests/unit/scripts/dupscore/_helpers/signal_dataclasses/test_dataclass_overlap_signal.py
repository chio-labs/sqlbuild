from __future__ import annotations

import pytest

from scripts.dupscore._helpers.facts import extract_project_facts
from scripts.dupscore._helpers.signal_dataclasses import score_dataclass_overlap
from scripts.dupscore.models import SignalRanking
from tests.unit.scripts.dupscore._helpers.signal_dataclasses._test_types import (
    DataclassOverlapPairTestCase,
    DataclassOverlapSuppressionTestCase,
)

_PLANNER_MODEL: str = (
    "from dataclasses import dataclass\n"
    "\n"
    "@dataclass(frozen=True)\n"
    "class PlanOptions:\n"
    "    select: str\n"
    "    exclude: str\n"
    "    full_refresh: bool\n"
    "    changes_only: bool\n"
    "    cli_vars: dict\n"
)
_EXECUTOR_MODEL: str = (
    "from dataclasses import dataclass\n"
    "\n"
    "@dataclass(frozen=True)\n"
    "class BuildOptions:\n"
    "    select: str\n"
    "    exclude: str\n"
    "    full_refresh: bool\n"
    "    changes_only: bool\n"
    "    concurrency: int\n"
)
_SMALL_MODEL: str = (
    "from dataclasses import dataclass\n"
    "\n"
    "@dataclass(frozen=True)\n"
    "class Tiny:\n"
    "    left: str\n"
    "    right: str\n"
)


@pytest.mark.parametrize(
    "test_case",
    [
        DataclassOverlapPairTestCase(
            description="ranks models sharing at least four field names",
            sources={
                "src/sqlbuild/alpha/planner/models.py": _PLANNER_MODEL,
                "src/sqlbuild/alpha/executor/models.py": _EXECUTOR_MODEL,
            },
            expected_top_pair=("sqlbuild.alpha.executor", "sqlbuild.alpha.planner"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_overlapping_models_when_scoring_then_ranks_pair(
    test_case: DataclassOverlapPairTestCase,
) -> None:
    ranking: SignalRanking = score_dataclass_overlap(extract_project_facts(test_case.sources))

    assert ranking.entries[0].package_pair == test_case.expected_top_pair


@pytest.mark.parametrize(
    "test_case",
    [
        DataclassOverlapSuppressionTestCase(
            description="ignores models below the shared-field threshold",
            sources={
                "src/sqlbuild/alpha/planner/models.py": _SMALL_MODEL,
                "src/sqlbuild/alpha/executor/models.py": _SMALL_MODEL,
            },
            expected_entry_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_small_models_when_scoring_then_returns_no_pairs(
    test_case: DataclassOverlapSuppressionTestCase,
) -> None:
    ranking: SignalRanking = score_dataclass_overlap(extract_project_facts(test_case.sources))

    assert len(ranking.entries) == test_case.expected_entry_count
