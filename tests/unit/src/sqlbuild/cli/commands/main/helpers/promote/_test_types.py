from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FormatPromoteOutputTestCase:
    description: str
    status: str
    promoted_models: tuple[str, ...]
    remaining_stale: tuple[str, ...]
    verbose: bool
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = ()
