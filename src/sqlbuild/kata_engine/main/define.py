"""Public @kata custom-rule decorator."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.kata_engine._helpers.engine.definition import define_kata
from sqlbuild.kata_engine.models import RuleOption
from sqlbuild.kata_engine.types import KataCheck


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
    """Attach validated kata metadata while returning the check unchanged."""

    return define_kata(
        code=code,
        family=family,
        slug=slug,
        message=message,
        remediation=remediation,
        options=options,
        enabled_by_default=enabled_by_default,
    )
