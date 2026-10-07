"""Test case types for the differential harness corpus helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.compiler_differential.models import ExpectedOutcome


@dataclass(frozen=True)
class CorpusExpectationTestCase:
    """A corpus selection and the expectation each named entry must declare."""

    description: str
    corpora: tuple[str, ...]
    expected_outcomes: dict[str, ExpectedOutcome]


@dataclass(frozen=True)
class InlineCompileCodesTestCase:
    """The compile package and the codes every inline render-stage literal must belong to."""

    description: str
    compile_root: Path
    accounted_codes: frozenset[str]
    expected_unaccounted: dict[str, tuple[str, ...]]
