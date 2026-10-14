"""Test case types for the planner differential model-file edits."""

from __future__ import annotations

from dataclasses import dataclass

from scripts.planner_differential.models import ModelFile


@dataclass(frozen=True)
class SplitModelFileTestCase:
    """Model file text and the header and query the harness edits, or None."""

    description: str
    text: str
    expected_model_file: ModelFile | None


@dataclass(frozen=True)
class HeaderPropertyTestCase:
    """A MODEL header and the header after inserting one property line."""

    description: str
    header: str
    line: str
    expected_header: str


@dataclass(frozen=True)
class JoinModelFileTestCase:
    """A split model file and the text the harness writes back."""

    description: str
    model_file: ModelFile
    expected_text: str
