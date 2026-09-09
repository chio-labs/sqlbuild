"""Public @rule custom-rule decorator."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.rule_engine._helpers.engine.definition import define_rule
from sqlbuild.rule_engine.models import RuleOption
from sqlbuild.rule_engine.types import RuleCheck


def rule(
    *,
    code: str,
    message: str,
    remediation: str,
    slug: str | None = None,
    options: tuple[RuleOption[object], ...] = (),
    enabled_by_default: bool = False,
) -> Callable[[RuleCheck], RuleCheck]:
    """Attach validated rule metadata while returning the check unchanged."""

    return define_rule(
        code=code,
        slug=(slug if slug is not None else code.lower()),
        message=message,
        remediation=remediation,
        options=options,
        enabled_by_default=enabled_by_default,
    )
