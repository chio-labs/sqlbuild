"""Capability-bounded custom SQL lint rule context."""

from collections.abc import Mapping
from typing import Any

from sqlbuild.lint.exceptions import CustomLintError
from sqlbuild.lint.models import CustomLintFinding, CustomLintRule, LintRuleOption


class LintRuleContext:
    """Statement-only context with no SQLBuild project capabilities."""

    def __init__(
        self,
        *,
        source: str,
        dialect: str,
        ast: Any,
        rule: CustomLintRule,
        options: Mapping[str, object],
    ) -> None:
        self._source = source
        self._dialect = dialect
        self._ast = ast
        self._rule = rule
        self._options = options

    @property
    def source(self) -> str:
        return self._source

    @property
    def dialect(self) -> str:
        return self._dialect

    @property
    def ast(self) -> Any:
        return self._ast

    def option[T](self, option: LintRuleOption[T]) -> T:
        if option not in self._rule.options:
            raise CustomLintError(
                f"option {option.name} is not declared by custom lint rule {self._rule.code}"
            )
        value: object = self._options.get(option.name, option.default)
        if not isinstance(value, option.value_type):
            raise CustomLintError(
                f"option {option.name} for {self._rule.code} must be {option.value_type.__name__}"
            )
        return value

    def finding(
        self,
        *,
        start: int,
        end: int,
        message: str | None = None,
        remediation: str | None = None,
    ) -> CustomLintFinding:
        if start < 0 or end <= start or end > len(self._source):
            raise CustomLintError(
                f"custom lint rule {self._rule.code} produced invalid span {start}:{end}"
            )
        return CustomLintFinding(
            code=self._rule.code,
            start=start,
            end=end,
            message=message or self._rule.message,
            remediation=remediation or self._rule.remediation,
        )
