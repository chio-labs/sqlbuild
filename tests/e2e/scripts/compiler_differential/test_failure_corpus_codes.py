"""Every failure case emits its declared code as the first error, reaching every discovery code."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.compiler_differential._helpers.corpus.emitted_codes import (
    discovery_error_codes,
    emitted_failure_codes,
)
from scripts.compiler_differential.main.failure_cases import failure_cases
from scripts.compiler_differential.models import DifferentialOptions, EmittedCodes
from tests.e2e.scripts.compiler_differential._test_types import FailureCorpusCodesTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        FailureCorpusCodesTestCase(
            description="python_engine",
            expected_first_errors={
                f"failure/{case.name}": case.expected_code for case in failure_cases()
            },
            expected_warnings={"failure/built-in-audit-shadow": "P003"},
            expected_discovery_codes=discovery_error_codes(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failure_corpus_when_compiling_then_emitted_first_errors_match_and_cover_discovery(
    test_case: FailureCorpusCodesTestCase, tmp_path: Path
) -> None:
    emitted: dict[str, EmittedCodes] = emitted_failure_codes(
        options=DifferentialOptions(
            engines=("python", "python"),
            work_dir=tmp_path,
            jobs=4,
            stage_captures=False,
            python=Path(sys.executable),
            engine_environment={},
        )
    )

    first_errors: dict[str, str | None] = {
        name: codes.first_error for name, codes in emitted.items()
    }
    assert first_errors == test_case.expected_first_errors
    assert all(
        code in emitted[name].warnings for name, code in test_case.expected_warnings.items()
    ), emitted
    assert test_case.expected_discovery_codes <= set(first_errors.values())


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
