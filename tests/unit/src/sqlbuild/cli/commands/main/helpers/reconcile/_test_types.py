from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReconcileOutputTestCase:
    description: str
    message: str
    expected_text: str
    expected_color_fragments: tuple[str, ...]
