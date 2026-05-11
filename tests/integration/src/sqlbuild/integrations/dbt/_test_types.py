from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RealDbtRunnerTestCase:
    description: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    resource_types: tuple[str, ...]
    expected_unique_ids: tuple[str, ...]
