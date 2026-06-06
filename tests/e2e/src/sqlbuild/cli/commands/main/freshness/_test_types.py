from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FreshnessE2ETestCase:
    description: str
    expected_fragments: tuple[str, ...]
