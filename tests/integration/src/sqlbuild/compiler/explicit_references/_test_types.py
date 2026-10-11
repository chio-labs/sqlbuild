from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExplicitReferenceGoldenTestCase:
    """Projects whose explicit-reference outcomes must equal Python's recorded golden."""

    description: str
    projects: tuple[tuple[str, dict[str, str], str], ...]
    expected_codes: frozenset[str]
    expected_raised: int
