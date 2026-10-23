"""Test types for the review schema lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ReviewSchemaFoldingTestCase:
    """How a warehouse stores and compares schema names, and what the review must see."""

    description: str
    fold: Callable[[str], str]
    compare: Callable[[str], str]
    expected_dropped: bool
    expected_code: str
    expected_created_at: datetime
