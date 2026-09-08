"""Public @policy custom-rule decorator."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.policy_engine._helpers.engine.definition import define_policy
from sqlbuild.policy_engine.models import RuleOption
from sqlbuild.policy_engine.types import PolicyCheck


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
    """Attach validated policy metadata while returning the check unchanged."""

    return define_policy(
        code=code,
        family=family,
        slug=slug,
        message=message,
        remediation=remediation,
        options=options,
        enabled_by_default=enabled_by_default,
        project_wide=project_wide,
    )
