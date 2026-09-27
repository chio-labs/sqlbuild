from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TypeProofRuleSkipTestCase:
    description: str
    no_sql_analysis: bool
    settings_toml: str
    expected_skipped_rules: tuple[str, ...]
    expected_finding_codes: tuple[str, ...]
