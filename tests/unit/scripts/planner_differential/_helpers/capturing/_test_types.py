"""Test case types for the planner differential canonicalisation helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MaskTextTestCase:
    """Raw output text and the text after masking run-specific values."""

    description: str
    raw: str
    expected_text: str


@dataclass(frozen=True)
class CanonicalValueTestCase:
    """A decoded JSON value and its canonical form."""

    description: str
    value: object
    expected_value: object


@dataclass(frozen=True)
class StateDeltaTestCase:
    """State rows before and after a build and the rows the step gained and lost."""

    description: str
    before: dict[str, list[str]]
    after: dict[str, list[str]]
    expected_delta: dict[str, dict[str, list[object]]]


@dataclass(frozen=True)
class PlanCaptureTestCase:
    """A value written as a plan capture document and its canonical expanded form."""

    description: str
    value: object
    expected_value: object
