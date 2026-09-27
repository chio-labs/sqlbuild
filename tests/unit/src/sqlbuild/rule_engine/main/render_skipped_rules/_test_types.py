from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkippedTypeProofRulesNoteTestCase:
    description: str
    codes: tuple[str, ...]
    expected_note: str | None
