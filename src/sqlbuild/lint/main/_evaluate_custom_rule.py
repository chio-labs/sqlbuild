"""Single custom SQL lint rule evaluation entrypoint."""

from sqlbuild.lint._helpers.custom_rules import run_lint_rule
from sqlbuild.lint.models import CustomLintFinding, CustomLintRule
from sqlbuild.lint.types import CustomLintCheck


def evaluate_lint_rule(
    *,
    rule: CustomLintCheck | CustomLintRule,
    source: str,
    dialect: str = "generic",
) -> tuple[CustomLintFinding, ...]:
    """Evaluate one custom rule without project discovery."""

    return run_lint_rule(rule=rule, source=source, dialect=dialect)
