from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PausedCyclicCollectionTestCase:
    """Collector state before nested pauses and the states observed inside and after them."""

    description: str
    enabled_before: bool
    expected_inside_inner: bool
    expected_after_inner: bool
    expected_after_outer: bool
