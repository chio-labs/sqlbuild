from __future__ import annotations

import pytest

from scripts.dupscore._helpers.fusion import filter_report_to_domain, fuse_rankings
from scripts.dupscore.constants import (
    SIGNAL_NAME_CALLGRAPH,
    SIGNAL_NAME_DATACLASS_OVERLAP,
    SIGNAL_NAME_SAME_NAME,
)
from scripts.dupscore.models import DupscoreConfig, DupscoreReport
from tests.unit.scripts.dupscore._helpers.fusion._test_types import (
    DomainFilterTestCase,
    FuseRankingsTestCase,
)
from tests.unit.scripts.dupscore._helpers.fusion.helpers import ranking_of

_PAIR_A: tuple[str, str] = ("sqlbuild.alpha.executor", "sqlbuild.alpha.planner")
_PAIR_B: tuple[str, str] = ("sqlbuild.alpha.cli", "sqlbuild.alpha.executor")
_PAIR_C: tuple[str, str] = ("sqlbuild.beta.left", "sqlbuild.beta.right")


@pytest.mark.parametrize(
    "test_case",
    [
        FuseRankingsTestCase(
            description="pair hit by two signals outranks single-signal pairs",
            rankings=(
                ranking_of(signal_name=SIGNAL_NAME_CALLGRAPH, pairs=(_PAIR_B, _PAIR_A)),
                ranking_of(signal_name=SIGNAL_NAME_SAME_NAME, pairs=(_PAIR_A,)),
                ranking_of(signal_name=SIGNAL_NAME_DATACLASS_OVERLAP, pairs=(_PAIR_A, _PAIR_C)),
            ),
            config=DupscoreConfig(),
            expected_order=(_PAIR_A, _PAIR_B, _PAIR_C),
            expected_allowlisted_flags=(False, False, False),
        ),
        FuseRankingsTestCase(
            description="allowlisted pairs keep their reason and marker",
            rankings=(ranking_of(signal_name=SIGNAL_NAME_CALLGRAPH, pairs=(_PAIR_A,)),),
            config=DupscoreConfig(allowlisted_pairs={_PAIR_A: "intentional mirror"}),
            expected_order=(_PAIR_A,),
            expected_allowlisted_flags=(True,),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_rankings_when_fusing_then_returns_expected_order(
    test_case: FuseRankingsTestCase,
) -> None:
    report: DupscoreReport = fuse_rankings(
        rankings=test_case.rankings,
        config=test_case.config,
        revision_label="worktree",
    )

    assert tuple(entry.package_pair for entry in report.entries) == test_case.expected_order
    allowlisted_flags: tuple[bool, ...] = tuple(entry.allowlisted for entry in report.entries)
    assert allowlisted_flags == test_case.expected_allowlisted_flags


@pytest.mark.parametrize(
    "test_case",
    [
        DomainFilterTestCase(
            description="keeps only pairs mentioning the requested domain",
            rankings=(ranking_of(signal_name=SIGNAL_NAME_CALLGRAPH, pairs=(_PAIR_A, _PAIR_C)),),
            domain="alpha",
            expected_pair_count=1,
        ),
        DomainFilterTestCase(
            description="returns everything when no domain is requested",
            rankings=(ranking_of(signal_name=SIGNAL_NAME_CALLGRAPH, pairs=(_PAIR_A, _PAIR_C)),),
            domain=None,
            expected_pair_count=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_report_when_filtering_domain_then_returns_expected_pair_count(
    test_case: DomainFilterTestCase,
) -> None:
    report: DupscoreReport = fuse_rankings(
        rankings=test_case.rankings,
        config=DupscoreConfig(),
        revision_label="worktree",
    )

    filtered: DupscoreReport = filter_report_to_domain(report=report, domain=test_case.domain)

    assert filtered.total_pairs == test_case.expected_pair_count
