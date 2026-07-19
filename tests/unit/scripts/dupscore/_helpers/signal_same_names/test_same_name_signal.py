from __future__ import annotations

import pytest

from scripts.dupscore._helpers.facts import extract_project_facts
from scripts.dupscore._helpers.signal_same_names import score_same_name_symbols
from scripts.dupscore.models import SignalRanking
from tests.unit.scripts.dupscore._helpers.signal_same_names._test_types import (
    SameNamePairTestCase,
    SameNameSuppressionTestCase,
)

_TWIN_BODY: str = (
    "def resolve_target_relation(name: str) -> str:\n    return name.strip().lower()\n"
)
_MIXED_BODY: str = "def _hidden() -> int:\n    return 1\n\ndef run() -> int:\n    return 2\n"


@pytest.mark.parametrize(
    "test_case",
    [
        SameNamePairTestCase(
            description="ranks a cross-package public twin with similar bodies",
            sources={
                "src/sqlbuild/alpha/planner/targets.py": _TWIN_BODY,
                "src/sqlbuild/alpha/executor/rewrite.py": _TWIN_BODY,
            },
            expected_top_pair=("sqlbuild.alpha.executor", "sqlbuild.alpha.planner"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cross_package_twin_when_scoring_same_names_then_ranks_pair(
    test_case: SameNamePairTestCase,
) -> None:
    ranking: SignalRanking = score_same_name_symbols(extract_project_facts(test_case.sources))

    assert ranking.entries[0].package_pair == test_case.expected_top_pair


@pytest.mark.parametrize(
    "test_case",
    [
        SameNameSuppressionTestCase(
            description="filters same-package main and helpers wrapper twins",
            sources={
                "src/sqlbuild/alpha/planner/main/resolve.py": _TWIN_BODY,
                "src/sqlbuild/alpha/planner/_helpers/resolve.py": _TWIN_BODY,
            },
            expected_entry_count=0,
        ),
        SameNameSuppressionTestCase(
            description="ignores private and generic function names",
            sources={
                "src/sqlbuild/alpha/planner/one.py": _MIXED_BODY,
                "src/sqlbuild/alpha/executor/two.py": _MIXED_BODY,
            },
            expected_entry_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_wrapper_or_generic_names_when_scoring_same_names_then_suppresses_pairs(
    test_case: SameNameSuppressionTestCase,
) -> None:
    ranking: SignalRanking = score_same_name_symbols(extract_project_facts(test_case.sources))

    assert len(ranking.entries) == test_case.expected_entry_count
