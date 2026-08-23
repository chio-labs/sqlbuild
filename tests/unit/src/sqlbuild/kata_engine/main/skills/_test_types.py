"""Test case declarations for kata skill generation."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillFreshnessTestCase:
    description: str
    selected_rule: str
    changed_rule: str
    expected_fresh: bool
    expected_stale: bool


@dataclass(frozen=True)
class SkillDivergenceTestCase:
    description: str
    selected_rule: str
    local_edit: str
    expected_error: str
