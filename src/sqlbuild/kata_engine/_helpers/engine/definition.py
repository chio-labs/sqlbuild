"""Kata decorator implementation and metadata lookup."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import cast

from sqlbuild.kata_engine.constants import RULE_CHECK_PARAMETER_NAMES
from sqlbuild.kata_engine.exceptions import KataError
from sqlbuild.kata_engine.models import KataRule, RuleOption
from sqlbuild.kata_engine.types import KataCheck

_RULE_ATTRIBUTE: str = "__sqlbuild_kata_rule__"


def define_kata(
    *,
    code: str,
    family: str,
    slug: str,
    message: str,
    remediation: str,
    options: tuple[RuleOption[object], ...],
    enabled_by_default: bool,
) -> Callable[[KataCheck], KataCheck]:
    """Attach validated custom kata metadata while returning the check unchanged."""

    def decorate(check: KataCheck) -> KataCheck:
        if (
            not code.strip()
            or not family.strip()
            or not slug.strip()
            or not message.strip()
            or not remediation.strip()
        ):
            raise KataError(f"custom kata rule {code} has an incomplete metadata envelope")
        names: tuple[str, ...] = tuple(option.name for option in options)
        if len(names) != len(set(names)):
            raise KataError(f"custom kata rule {code} declares duplicate option names")
        parameters: tuple[inspect.Parameter, ...] = tuple(
            inspect.signature(check).parameters.values()
        )
        if tuple(parameter.name for parameter in parameters) != RULE_CHECK_PARAMETER_NAMES or any(
            parameter.kind is not inspect.Parameter.KEYWORD_ONLY for parameter in parameters
        ):
            raise KataError(
                f"custom kata rule {code} must use def check(*, model, ctx: RuleContext)"
            )
        rule: KataRule = KataRule(
            code=code,
            family=family,
            slug=slug,
            message=message,
            remediation=remediation,
            check=check,
            options=options,
            enabled_by_default=enabled_by_default,
            custom=True,
        )
        _ = setattr(check, _RULE_ATTRIBUTE, rule)
        return check

    return decorate


def rule_from_value(*, value: object) -> KataRule | None:
    """Return attached kata metadata for one decorated value."""

    rule: object = getattr(value, _RULE_ATTRIBUTE, None)
    return cast(KataRule, rule) if isinstance(rule, KataRule) else None
