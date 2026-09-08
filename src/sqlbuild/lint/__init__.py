"""Public SQLBuild statement-local lint rule API."""

from sqlbuild.lint.classes.rule_context import LintRuleContext
from sqlbuild.lint.main._define_custom_rule import lint_rule
from sqlbuild.lint.main._evaluate_custom_rule import evaluate_lint_rule
from sqlbuild.lint.models import CustomLintFinding, LintRuleOption

__all__ = (
    "CustomLintFinding",
    "LintRuleContext",
    "LintRuleOption",
    "evaluate_lint_rule",
    "lint_rule",
)
