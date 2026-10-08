"""Every failure case emits its declared first error, reaching every discovery, render and
analysis code."""

from __future__ import annotations

import sys
from itertools import chain
from pathlib import Path

import pytest

import sqlbuild.compiler as compiler_package
from scripts.compiler_differential._helpers.corpus.emitted_codes import (
    analysis_error_codes,
    discovery_error_codes,
    emitted_failure_codes,
    render_error_codes,
)
from scripts.compiler_differential.constants import (
    ANALYSIS_UNREACHABLE_CODES,
    DISCOVERY_UNREACHABLE_CODES,
    RENDER_UNREACHABLE_CODES,
)
from scripts.compiler_differential.main.failure_cases import failure_cases
from scripts.compiler_differential.models import DifferentialOptions, EmittedCodes
from tests.e2e.scripts.compiler_differential._test_types import FailureCorpusCodesTestCase

_COMPILER_ROOT: Path = Path(compiler_package.__file__).parent


@pytest.mark.parametrize(
    "test_case",
    [
        FailureCorpusCodesTestCase(
            description="python_engine",
            expected_first_errors={
                f"failure/{case.name}": case.expected_code for case in failure_cases()
            },
            expected_first_messages={
                f"failure/{case.name}": case.expected_message
                for case in failure_cases()
                if case.expected_message is not None
            },
            expected_warnings={
                f"failure/{case.name}": case.expected_warning_code
                for case in failure_cases()
                if case.expected_warning_code is not None
            },
            expected_discovery_codes=discovery_error_codes()
            - frozenset(DISCOVERY_UNREACHABLE_CODES),
            expected_render_codes=render_error_codes() - frozenset(RENDER_UNREACHABLE_CODES),
            unreachable_render_codes=frozenset(RENDER_UNREACHABLE_CODES),
            expected_first_helps={
                f"failure/{case.name}": case.expected_help
                for case in failure_cases()
                if case.expected_help is not None
            },
            expected_first_notes={
                f"failure/{case.name}": frozenset(case.expected_notes)
                for case in failure_cases()
                if case.expected_notes
            },
            expected_first_locations={
                f"failure/{case.name}": case.expected_location
                for case in failure_cases()
                if case.expected_location is not None
            },
            expected_code_orders={
                f"failure/{case.name}": case.expected_codes
                for case in failure_cases()
                if case.expected_codes is not None
            },
            expected_analysis_codes=analysis_error_codes(_COMPILER_ROOT)
            - frozenset(ANALYSIS_UNREACHABLE_CODES),
            unreachable_analysis_codes=frozenset(ANALYSIS_UNREACHABLE_CODES),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failure_corpus_when_compiling_then_first_errors_match_and_cover_every_stage(
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
    first_messages: dict[str, str] = {
        name: emitted[name].first_error_message or "" for name in test_case.expected_first_messages
    }
    assert all(
        fragment in first_messages[name]
        for name, fragment in test_case.expected_first_messages.items()
    ), first_messages
    reached: set[str | None] = {
        *first_errors.values(),
        *chain.from_iterable(codes.warnings for codes in emitted.values()),
    }
    assert test_case.expected_discovery_codes <= set(first_errors.values())
    assert test_case.expected_render_codes <= reached, test_case.expected_render_codes - reached
    assert not test_case.unreachable_render_codes & set(first_errors.values())
    assert test_case.unreachable_render_codes <= render_error_codes()
    assert all(
        fragment in (emitted[name].first_error_help or "")
        for name, fragment in test_case.expected_first_helps.items()
    ), {name: emitted[name].first_error_help for name in test_case.expected_first_helps}
    assert all(
        notes <= set(emitted[name].first_error_notes)
        for name, notes in test_case.expected_first_notes.items()
    ), {name: emitted[name].first_error_notes for name in test_case.expected_first_notes}
    assert {
        name: emitted[name].first_error_location for name in test_case.expected_first_locations
    } == test_case.expected_first_locations
    assert {
        name: emitted[name].codes for name in test_case.expected_code_orders
    } == test_case.expected_code_orders
    assert test_case.expected_analysis_codes <= reached, test_case.expected_analysis_codes - reached
    assert not test_case.unreachable_analysis_codes & set(first_errors.values())
    assert test_case.unreachable_analysis_codes <= analysis_error_codes(_COMPILER_ROOT)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
