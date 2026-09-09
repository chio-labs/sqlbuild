"""Rules decorator implementation and metadata lookup."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import cast, get_type_hints

from sqlbuild.rule_engine.exceptions import RulesError
from sqlbuild.rule_engine.models import Model, Project, Rule, RuleOption
from sqlbuild.rule_engine.types import RuleCheck, RuleContext, RuleSubject

_RULE_PARAMETER_COUNT: int = 2
_RULE_CODE_DIGIT_COUNT: int = 3

_RULE_ATTRIBUTE: str = "__sqlbuild_rule__"


def define_rule(
    *,
    code: str,
    message: str,
    remediation: str,
    slug: str,
    options: tuple[RuleOption[object], ...],
    enabled_by_default: bool,
) -> Callable[[RuleCheck], RuleCheck]:
    """Attach custom rule metadata while deferring annotation resolution until discovery."""

    def decorate(check: RuleCheck) -> RuleCheck:
        if not code.strip() or not slug.strip() or not message.strip() or not remediation.strip():
            raise RulesError(f"custom rule {code} has an incomplete metadata envelope")
        if not _custom_code_is_valid(code):
            raise RulesError(f"custom rule code must match XSQBR<letters><three digits>: {code}")
        names: tuple[str, ...] = tuple(option.name for option in options)
        if len(names) != len(set(names)):
            raise RulesError(f"custom rule {code} declares duplicate option names")
        parameters: tuple[inspect.Parameter, ...] = tuple(
            inspect.signature(check).parameters.values()
        )
        if len(parameters) != _RULE_PARAMETER_COUNT or any(
            parameter.kind is not inspect.Parameter.KEYWORD_ONLY for parameter in parameters
        ):
            raise RulesError(
                f"custom rule {code} must accept exactly one typed Model or Project subject "
                "and one typed RuleContext as keyword-only parameters"
            )
        rule: Rule = Rule(
            code=code,
            family=code[:-3],
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


def resolve_rule_signature(*, rule: Rule) -> Rule:
    """Resolve one decorated rule's typed subject and context parameters."""

    try:
        hints: dict[str, object] = get_type_hints(rule.check)
    except (NameError, TypeError) as error:
        raise RulesError(
            f"could not resolve custom rule {rule.code} annotations: {error}"
        ) from error
    parameters: tuple[inspect.Parameter, ...] = tuple(
        inspect.signature(rule.check).parameters.values()
    )
    subjects: list[tuple[str, RuleSubject]] = []
    contexts: list[str] = []
    for parameter in parameters:
        annotation: object = hints.get(parameter.name, parameter.annotation)
        if annotation is Model:
            subjects.append((parameter.name, RuleSubject.MODEL))
        elif annotation is Project:
            subjects.append((parameter.name, RuleSubject.PROJECT))
        elif annotation is RuleContext:
            contexts.append(parameter.name)
    if len(subjects) != 1 or len(contexts) != 1:
        raise RulesError(
            f"custom rule {rule.code} must accept exactly one typed Model or Project subject "
            "and one typed RuleContext as keyword-only parameters"
        )
    subject_parameter, subject = subjects[0]
    return Rule(
        code=rule.code,
        family=rule.family,
        slug=rule.slug,
        message=rule.message,
        remediation=rule.remediation,
        check=rule.check,
        options=rule.options,
        enabled_by_default=rule.enabled_by_default,
        custom=rule.custom,
        source=rule.source,
        subject=subject,
        subject_parameter=subject_parameter,
        context_parameter=contexts[0],
        guidance=rule.guidance,
    )


def _custom_code_is_valid(code: str) -> bool:
    if len(code) < len("XSQBR") + _RULE_CODE_DIGIT_COUNT:
        return False
    prefix: str = code[:-_RULE_CODE_DIGIT_COUNT]
    number: str = code[-_RULE_CODE_DIGIT_COUNT:]
    suffix: str = prefix.removeprefix("XSQBR")
    family_is_valid: bool = not suffix or (
        suffix.isascii() and suffix.isalpha() and suffix.upper() == suffix
    )
    return (
        prefix.startswith("XSQBR")
        and family_is_valid
        and number.isascii()
        and number.isdecimal()
        and len(number) == _RULE_CODE_DIGIT_COUNT
    )


def rule_from_value(*, value: object) -> Rule | None:
    """Return attached rule metadata for one decorated value."""

    rule: object = getattr(value, _RULE_ATTRIBUTE, None)
    return cast(Rule, rule) if isinstance(rule, Rule) else None
