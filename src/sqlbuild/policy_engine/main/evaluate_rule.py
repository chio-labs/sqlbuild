"""Public custom policy rule test harness."""

from sqlbuild.policy_engine._helpers.engine.rule_harness import run_rule_case
from sqlbuild.policy_engine.models import PolicyRule, RuleCase, RuleResult
from sqlbuild.policy_engine.types import PolicyCheck


def evaluate_rule(*, rule: PolicyCheck | PolicyRule, test_case: RuleCase) -> RuleResult:
    """Evaluate one rule through discovery, compilation, and policy evaluation."""

    return run_rule_case(rule=rule, test_case=test_case)
