"""Test case declarations for the public rule harness."""

from dataclasses import dataclass

from sqlbuild.rules.testing import RuleCase


@dataclass(frozen=True)
class EvaluateRuleTestCase:
    description: str
    rule_case: RuleCase
    expected_code: str
    expected_path: str


@dataclass(frozen=True)
class EvaluateRuleParityTestCase:
    description: str
    rule_case: RuleCase
    expected_finding_count: int


@dataclass(frozen=True)
class EvaluateRuleDeterminismTestCase:
    description: str
    rule_case: RuleCase
    expected_error_pattern: str


@dataclass(frozen=True)
class AuthoringImportTestCase:
    description: str
    imported_module: str
    checked_modules: tuple[str, ...]
    expected_loaded_modules: tuple[str, ...]
