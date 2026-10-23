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


@dataclass(frozen=True)
class FoldedDescriptionTestCase:
    """Project files with prose descriptions and the folded text the manifest stores."""

    description: str
    files: dict[str, str]
    expected_description: str
    expected_column_descriptions: dict[str, str]
