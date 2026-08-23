"""Public custom kata rule test harness."""

from sqlbuild.kata_engine._helpers.engine.rule_harness import run_rule_case
from sqlbuild.kata_engine.models import KataRule, RuleCase, RuleResult
from sqlbuild.kata_engine.types import KataCheck


def evaluate_rule(*, rule: KataCheck | KataRule, test_case: RuleCase) -> RuleResult:
    """Evaluate one rule through discovery, compilation, and kata evaluation."""

    return run_rule_case(rule=rule, test_case=test_case)
