"""The failure corpus stays broad, uniquely named, and writes complete projects."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.compiler_differential.main.failure_cases import failure_cases
from scripts.compiler_differential.models import FailureCase
from tests.unit.scripts.compiler_differential.main._test_types import (
    FailureCaseWriteTestCase,
    FailureCorpusTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        FailureCorpusTestCase(
            description="breadth",
            expected_min_cases=45,
            expected_min_codes=30,
            expected_min_families=7,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failure_corpus_when_listing_then_names_are_unique_and_codes_are_broad(
    test_case: FailureCorpusTestCase,
) -> None:
    cases: tuple[FailureCase, ...] = failure_cases()
    codes: set[str] = {case.expected_code for case in cases}

    assert len({case.name for case in cases}) == len(cases)
    assert len(cases) >= test_case.expected_min_cases
    assert len(codes) >= test_case.expected_min_codes
    assert len({code.rstrip("0123456789") for code in codes}) >= test_case.expected_min_families


@pytest.mark.parametrize(
    "test_case",
    [
        FailureCaseWriteTestCase(
            description=case.name, case=case, expected_files=tuple(sorted(case.files))
        )
        for case in failure_cases()
    ],
    ids=lambda case: case.description,
)
def test_given_failure_case_when_writing_then_every_file_exists(
    test_case: FailureCaseWriteTestCase, tmp_path: Path
) -> None:
    test_case.case.write(tmp_path)

    assert (
        tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*.*")))
        == test_case.expected_files
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
