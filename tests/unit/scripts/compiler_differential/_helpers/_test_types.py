"""Test case types for the differential harness comparison helpers."""

from __future__ import annotations

from dataclasses import dataclass

from scripts.compiler_differential.models import ExpectedOutcome


@dataclass(frozen=True)
class JsonDifferenceTestCase:
    """Two JSON documents and where the harness must report their first difference."""

    description: str
    left: object
    right: object
    expected_location: str | None


@dataclass(frozen=True)
class TextDifferenceTestCase:
    """Two texts and the first differing line the harness must report."""

    description: str
    left: str
    right: str
    expected_location: str | None


@dataclass(frozen=True)
class PreviewTestCase:
    """A long differing value and the bounded preview the report shows."""

    description: str
    left: object
    right: object
    expected_max_length: int
    expected_suffix: str


@dataclass(frozen=True)
class NormalizationTestCase:
    """Raw output and the normalized text the harness compares."""

    description: str
    raw: str
    expected_text: str


@dataclass(frozen=True)
class PayloadStripTestCase:
    """A decoded report or manifest and what remains once volatile fields are removed."""

    description: str
    payload: object
    expected_payload: object


@dataclass(frozen=True)
class EngineEnvironmentTestCase:
    """Repeated --engine-env values and the per-engine overrides they produce."""

    description: str
    values: tuple[str, ...]
    expected_environment: dict[str, dict[str, str]]


@dataclass(frozen=True)
class EngineEnvironmentErrorTestCase:
    """A malformed --engine-env value and the usage error it raises."""

    description: str
    value: str
    expected_message: str


@dataclass(frozen=True)
class ExpectedOutcomeTestCase:
    """One --expect value and the outcome it parses to."""

    description: str
    value: str
    expected_outcome: ExpectedOutcome


@dataclass(frozen=True)
class ExpectedOutcomeErrorTestCase:
    """One malformed --expect value."""

    description: str
    value: str
    expected_message: str


@dataclass(frozen=True)
class CorpusExpectationTestCase:
    """A corpus selection and the expectation each named entry must declare."""

    description: str
    corpora: tuple[str, ...]
    expected_outcomes: dict[str, ExpectedOutcome]
