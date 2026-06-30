from __future__ import annotations

import pytest

from sqlbuild.shared.main.summary_footer import format_summary_footer
from tests.unit.src.sqlbuild.shared.main._test_types import SummaryFooterTestCase

SUMMARY_FOOTER_TEST_CASES: tuple[SummaryFooterTestCase, ...] = (
    SummaryFooterTestCase(
        description="formats summary counts with semantic colors",
        counts=(
            ("PASS", 2),
            ("WARN", 1),
            ("FAIL", 0),
            ("SKIP", 3),
            ("TOTAL", 6),
        ),
        elapsed="0.12s",
        expected_no_color="PASS=2  WARN=1  FAIL=0  SKIP=3  TOTAL=6  (0.12s)",
        expected_color_fragments=(
            "\033[2mPASS=\033[0m\033[32m2\033[0m",
            "\033[2mWARN=\033[0m\033[33m1\033[0m",
            "\033[2mFAIL=\033[0m\033[31m0\033[0m",
            "\033[2mSKIP=\033[0m\033[2m3\033[0m",
            "\033[2mTOTAL=\033[0m\033[34m\033[1m6\033[0m",
            "\033[2m(0.12s)\033[0m",
        ),
    ),
    SummaryFooterTestCase(
        description="formats prefixed status counts semantically",
        counts=(
            ("SYNC_PASS", 2),
            ("SYNC_FAIL", 0),
        ),
        elapsed=None,
        expected_no_color="SYNC_PASS=2  SYNC_FAIL=0",
        expected_color_fragments=(
            "\033[2mSYNC_PASS=\033[0m\033[32m2\033[0m",
            "\033[2mSYNC_FAIL=\033[0m\033[31m0\033[0m",
        ),
    ),
)


@pytest.mark.parametrize(
    "test_case",
    SUMMARY_FOOTER_TEST_CASES,
    ids=[case.description for case in SUMMARY_FOOTER_TEST_CASES],
)
def test_given_summary_counts_when_formatting_then_uses_semantic_colors(
    test_case: SummaryFooterTestCase,
) -> None:
    no_color: str = format_summary_footer(
        counts=test_case.counts,
        use_color=False,
        elapsed=test_case.elapsed,
    )
    color: str = format_summary_footer(
        counts=test_case.counts,
        use_color=True,
        elapsed=test_case.elapsed,
    )

    assert no_color == test_case.expected_no_color
    fragment: str
    for fragment in test_case.expected_color_fragments:
        assert fragment in color
