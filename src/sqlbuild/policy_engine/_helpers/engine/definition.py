"""Policy decorator implementation and metadata lookup."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import cast

from sqlbuild.policy_engine.constants import RULE_CHECK_PARAMETER_NAMES
from sqlbuild.policy_engine.exceptions import PolicyError
from sqlbuild.policy_engine.models import PolicyRule, RuleOption
from sqlbuild.policy_engine.types import PolicyCheck

_RULE_ATTRIBUTE: str = "__sqlbuild_policy_rule__"


def define_policy(
    *,
    code: str,
    family: str,
    slug: str,
    message: str,
    remediation: str,
    options: tuple[RuleOption[object], ...],
    enabled_by_default: bool,
    project_wide: bool,
) -> Callable[[PolicyCheck], PolicyCheck]:
    """Attach validated custom policy metadata while returning the check unchanged."""

    def decorate(check: PolicyCheck) -> PolicyCheck:
        if (
            not code.strip()
            or not family.strip()
            or not slug.strip()
            or not message.strip()
            or not remediation.strip()
        ):
            raise PolicyError(f"custom policy rule {code} has an incomplete metadata envelope")
        names: tuple[str, ...] = tuple(option.name for option in options)
        if len(names) != len(set(names)):
            raise PolicyError(f"custom policy rule {code} declares duplicate option names")
        parameters: tuple[inspect.Parameter, ...] = tuple(
            inspect.signature(check).parameters.values()
        )
        if tuple(parameter.name for parameter in parameters) != RULE_CHECK_PARAMETER_NAMES or any(
            parameter.kind is not inspect.Parameter.KEYWORD_ONLY for parameter in parameters
        ):
            raise PolicyError(
                f"custom policy rule {code} must use def check(*, model, ctx: RuleContext)"
            )
        rule: PolicyRule = PolicyRule(
            code=code,
            family=family,
            slug=slug,
            message=message,
            remediation=remediation,
            check=check,
            options=options,
            enabled_by_default=enabled_by_default,
            custom=True,
            project_wide=project_wide,
        )
        _ = setattr(check, _RULE_ATTRIBUTE, rule)
        return check

    return decorate


def rule_from_value(*, value: object) -> PolicyRule | None:
    """Return attached policy metadata for one decorated value."""

    rule: object = getattr(value, _RULE_ATTRIBUTE, None)
    return cast(PolicyRule, rule) if isinstance(rule, PolicyRule) else None
