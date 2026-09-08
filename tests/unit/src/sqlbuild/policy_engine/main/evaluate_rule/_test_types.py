"""Test case declarations for the public policy rule harness."""

from dataclasses import dataclass

from sqlbuild.policy import RuleCase


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
    expected_fault_count: int
