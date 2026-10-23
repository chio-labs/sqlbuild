"""Test case types for header string quoting and folding E2E tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HeaderQuoteErrorTestCase:
    """One project file whose header string is quoted wrongly, and the error compile reports."""

    description: str
    path: str
    contents: str
    expected_code: str
    expected_location: str
    expected_message: str
