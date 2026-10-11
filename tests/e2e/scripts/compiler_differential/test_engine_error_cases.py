"""Every engine reports each shared user-facing error with the same exact code, text and help.

Ports add cases to `engine_error_cases()` in the failure corpus, not here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.compiler_differential._helpers.corpus.emitted_codes import case_emitted_codes
from scripts.compiler_differential._helpers.corpus.failure_cases import engine_error_cases
from scripts.compiler_differential.models import DifferentialOptions, EmittedCodes
from tests.e2e.scripts.compiler_differential._test_types import EngineErrorCaseTestCase

_ENGINES: tuple[str, ...] = ("native", "native-preview")


@pytest.mark.parametrize(
    "test_case",
    [
        EngineErrorCaseTestCase(description=case.name, expected_error_case=case)
        for case in engine_error_cases()
    ],
    ids=lambda case: case.description,
)
def test_given_shared_error_case_when_compiling_on_every_engine_then_error_text_is_exact(
    test_case: EngineErrorCaseTestCase, tmp_path: Path
) -> None:
    emitted: dict[str, EmittedCodes] = {
        engine: case_emitted_codes(
            case=test_case.expected_error_case,
            options=DifferentialOptions(
                engines=(engine, engine),
                work_dir=tmp_path / engine,
                jobs=1,
                stage_captures=False,
                python=Path(sys.executable),
                engine_environment={},
            ),
        )
        for engine in _ENGINES
    }

    assert {
        engine: (codes.first_error, codes.first_error_message, codes.first_error_help)
        for engine, codes in emitted.items()
    } == {
        engine: (
            test_case.expected_error_case.expected_code,
            test_case.expected_error_case.expected_message,
            test_case.expected_error_case.expected_help,
        )
        for engine in _ENGINES
    }


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
