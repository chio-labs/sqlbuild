"""Public custom rule test harness."""

from sqlbuild.rule_engine._helpers.engine.rule_harness import run_rule_case
from sqlbuild.rule_engine.models import Rule, RuleCase, RuleResult
from sqlbuild.rule_engine.types import RuleCheck


def evaluate_rule(*, rule: RuleCheck | Rule, test_case: RuleCase) -> RuleResult:
    """Evaluate one rule through discovery, compilation, and rule evaluation."""

    return run_rule_case(rule=rule, test_case=test_case)
