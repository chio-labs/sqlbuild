"""Public SQLBuild kata rule-authoring and testing API."""

from collections.abc import Callable

from sqlbuild.kata_engine.main.define import kata as _kata
from sqlbuild.kata_engine.main.evaluate_rule import evaluate_rule as _evaluate_rule
from sqlbuild.kata_engine.models import (
    KataFault,
    KataResult,
    KataRule,
    RuleCase,
    RuleFile,
    RuleOption,
    RuleResult,
)
from sqlbuild.kata_engine.types import KataCheck, RuleContext

__all__ = (
    "KataFault",
    "KataResult",
    "RuleCase",
    "RuleContext",
    "RuleFile",
    "RuleOption",
    "RuleResult",
    "evaluate_rule",
    "kata",
)


def kata(
    *,
    code: str,
    family: str,
    slug: str,
    message: str,
    remediation: str,
    options: tuple[RuleOption[object], ...] = (),
    enabled_by_default: bool = False,
) -> Callable[[KataCheck], KataCheck]:
    """Declare one repository-owned custom kata rule."""

    return _kata(
        code=code,
        family=family,
        slug=slug,
        message=message,
        remediation=remediation,
        options=options,
        enabled_by_default=enabled_by_default,
    )


def evaluate_rule(*, rule: KataCheck | KataRule, test_case: RuleCase) -> RuleResult:
    """Evaluate one custom rule through the public kata test harness."""

    return _evaluate_rule(rule=rule, test_case=test_case)
