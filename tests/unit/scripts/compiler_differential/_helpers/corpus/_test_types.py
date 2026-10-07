"""Test case types for the differential harness corpus helpers."""

from __future__ import annotations

from dataclasses import dataclass

from scripts.compiler_differential.models import ExpectedOutcome


@dataclass(frozen=True)
class CorpusExpectationTestCase:
    """A corpus selection and the expectation each named entry must declare."""

    description: str
    corpora: tuple[str, ...]
    expected_outcomes: dict[str, ExpectedOutcome]
