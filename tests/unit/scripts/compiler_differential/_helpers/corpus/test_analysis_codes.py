"""The analysis code scan finds every B, K, S and syntax code, and documents each unreachable one."""

from __future__ import annotations

from pathlib import Path

import pytest

import sqlbuild.compiler as compiler_package
from scripts.compiler_differential._helpers.analysis_corpus.failure_cases import (
    analysis_failure_cases,
)
from scripts.compiler_differential._helpers.corpus.emitted_codes import analysis_error_codes
from scripts.compiler_differential.constants import ANALYSIS_UNREACHABLE_CODES
from scripts.compiler_differential.main.failure_cases import failure_cases
from scripts.compiler_differential.models import FailureCase
from tests.unit.scripts.compiler_differential._helpers.corpus._test_types import (
    AnalysisCodesTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        AnalysisCodesTestCase(
            description="compiler_package",
            compiler_root=Path(compiler_package.__file__).parent,
            expected_codes=frozenset(
                {
                    *(f"B00{number}" for number in (0, 2, 3, 4, 5)),
                    "B101",
                    "B102",
                    *(f"B2{number}" for number in range(10, 20)),
                    *(f"B23{number}" for number in range(5)),
                    "B300",
                    "B301",
                    "B302",
                    *(f"K00{number}" for number in range(1, 7)),
                    "K011",
                    "P001",
                    "P003",
                    "S101",
                    "S102",
                    "S103",
                    "S104",
                }
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_compiler_when_scanning_analysis_codes_then_each_is_cased_or_unreachable(
    test_case: AnalysisCodesTestCase,
) -> None:
    codes: frozenset[str] = analysis_error_codes(test_case.compiler_root)
    cases: tuple[FailureCase, ...] = (*failure_cases(), *analysis_failure_cases())
    cased: set[str | None] = {case.expected_code for case in cases} | {
        case.expected_warning_code for case in cases
    }

    assert test_case.expected_codes <= codes, test_case.expected_codes - codes
    assert set(ANALYSIS_UNREACHABLE_CODES) <= codes
    assert all(reason.strip() for reason in ANALYSIS_UNREACHABLE_CODES.values())
    assert codes - set(ANALYSIS_UNREACHABLE_CODES) <= cased, (
        codes - set(ANALYSIS_UNREACHABLE_CODES) - cased
    )
    assert not set(ANALYSIS_UNREACHABLE_CODES) & {case.expected_code for case in cases}


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
