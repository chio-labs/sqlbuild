from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FormatRollbackOutputTestCase:
    description: str
    status: str
    rolled_back_models: tuple[str, ...]
    verbose: bool
    expected_fragments: tuple[str, ...]
    expected_color_fragments: tuple[str, ...] = ()
    unexpected_fragments: tuple[str, ...] = ()
