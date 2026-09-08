"""Public custom SQL lint rule definition."""

from collections.abc import Callable

from sqlbuild.lint._helpers.custom_rules import define_lint_rule
from sqlbuild.lint.models import LintRuleOption
from sqlbuild.lint.types import CustomLintCheck


def lint_rule(
    *,
    code: str,
    family: str,
    slug: str,
    message: str,
    remediation: str,
    options: tuple[LintRuleOption[object], ...] = (),
) -> Callable[[CustomLintCheck], CustomLintCheck]:
    """Declare one repository-owned statement-local lint rule."""

    return define_lint_rule(
        code=code,
        family=family,
        slug=slug,
        message=message,
        remediation=remediation,
        options=options,
    )
