"""Public SQLBuild policy rule-authoring and testing API."""

from collections.abc import Callable

from sqlbuild.policy_engine.main.define import policy as _policy
from sqlbuild.policy_engine.main.evaluate_rule import evaluate_rule as _evaluate_rule
from sqlbuild.policy_engine.models import (
    PolicyFault,
    PolicyResult,
    PolicyRule,
    RuleCase,
    RuleFile,
    RuleOption,
    RuleResult,
)
from sqlbuild.policy_engine.types import PolicyCheck, RuleContext

__all__ = (
    "PolicyFault",
    "PolicyResult",
    "RuleCase",
    "RuleContext",
    "RuleFile",
    "RuleOption",
    "RuleResult",
    "evaluate_rule",
    "policy",
)


def policy(
    *,
    code: str,
    family: str,
    slug: str,
    message: str,
    remediation: str,
    options: tuple[RuleOption[object], ...] = (),
    enabled_by_default: bool = False,
    project_wide: bool = False,
) -> Callable[[PolicyCheck], PolicyCheck]:
    """Declare one repository-owned custom policy rule."""

    return _policy(
        code=code,
        family=family,
        slug=slug,
        message=message,
        remediation=remediation,
        options=options,
        enabled_by_default=enabled_by_default,
        project_wide=project_wide,
    )


def evaluate_rule(*, rule: PolicyCheck | PolicyRule, test_case: RuleCase) -> RuleResult:
    """Evaluate one custom rule through the public policy test harness."""

    return _evaluate_rule(rule=rule, test_case=test_case)
