from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RulesProgressTestCase:
    description: str
    elapsed_seconds: float
    built_in_ms: int
    custom_ms: int
    expected_message: str
    skipped_type_proof_rules: tuple[str, ...] = ()
    note_skipped_rules: bool = False
