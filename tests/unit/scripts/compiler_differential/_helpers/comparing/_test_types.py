"""Test case types for the differential harness comparing helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


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
class CaptureDifferenceTestCase:
    """Two frontier values captured to disk and where their first difference must be reported."""

    description: str
    left: Callable[[], object]
    right: Callable[[], object]
    expected_location: str | None


@dataclass(frozen=True)
class CaptureTextDifferenceTestCase:
    """Two capture files that are not both JSON and the first differing line to report."""

    description: str
    left: str
    right: str
    expected_location: str | None


@dataclass(frozen=True)
class CapturePreviewTestCase:
    """Two captures whose first difference is a missing value and the preview it must show."""

    description: str
    left: Callable[[], object]
    right: Callable[[], object]
    expected_location: str
    expected_left_prefix: str
