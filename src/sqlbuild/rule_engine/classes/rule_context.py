"""Concrete context exposing immutable compiler facts to one custom rule invocation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.rule_engine.classes.audit_facts import AuditFacts
from sqlbuild.rule_engine.classes.column_facts import ColumnFacts
from sqlbuild.rule_engine.classes.contract_facts import ContractFacts
from sqlbuild.rule_engine.classes.declaration_facts import DeclarationFacts
from sqlbuild.rule_engine.classes.graph_facts import GraphFacts
from sqlbuild.rule_engine.classes.model_test_facts import TestFacts
from sqlbuild.rule_engine.classes.project_facts import ProjectFacts
from sqlbuild.rule_engine.classes.sql_facts import SqlFacts
from sqlbuild.rule_engine.constants import PARENT_DIRECTORY_TOKEN
from sqlbuild.rule_engine.exceptions import RuleUsageError
from sqlbuild.rule_engine.models import (
    Finding,
    Model,
    ProjectPath,
    Rule,
    RuleFactViews,
    RuleOption,
    RulesConfig,
    SqlNode,
)


def build_rule_fact_views(
    *, project: CompiledProject, project_dir: Path, dialect: str
) -> RuleFactViews:
    """Build immutable views once for one compiled project snapshot."""

    return RuleFactViews(
        project=ProjectFacts(project=project, project_dir=project_dir),
        sql=SqlFacts(dialect=dialect, project=project),
        graph=GraphFacts(project=project),
        columns=ColumnFacts(project=project),
        contracts=ContractFacts(project=project),
        tests=TestFacts(project=project),
        audits=AuditFacts(project=project),
        declarations=DeclarationFacts(project=project),
    )


class EvaluationRuleContext:
    """Typed compiler-fact views and finding construction for one active rule."""

    def __init__(
        self,
        *,
        model: CompiledModel | None,
        rule: Rule,
        config: RulesConfig,
        project: CompiledProject,
        project_dir: Path,
        selected_rules: tuple[Rule, ...],
        dialect: str,
        facts: RuleFactViews | None = None,
    ) -> None:
        del model, selected_rules
        self._rule = rule
        self._config = config
        views: RuleFactViews = facts or build_rule_fact_views(
            project=project, project_dir=project_dir, dialect=dialect
        )
        self.project = views.project
        self.sql = views.sql
        self.graph = views.graph
        self.columns = views.columns
        self.contracts = views.contracts
        self.tests = views.tests
        self.audits = views.audits
        self.declarations = views.declarations

    def option[T](self, option: RuleOption[T]) -> T:
        """Return one declared option after native configuration validation."""

        if option not in self._rule.options:
            raise RuleUsageError(f"option {option.name} is not declared by rule {self._rule.code}")
        value: object = self._config.rule_options.get(self._rule.code, {}).get(
            option.name, option.default
        )
        return cast(T, value)

    def finding(
        self,
        *,
        subject: Model | ProjectPath | Path | str,
        node: SqlNode | Any | None = None,
        line: int | None = None,
        column: int | None = None,
        message: str | None = None,
        remediation: str | None = None,
    ) -> Finding:
        """Build one deterministic finding against a compiler-owned subject or project path."""

        path: Path
        if isinstance(subject, Model):
            path = subject.path
        elif isinstance(subject, ProjectPath):
            path = Path(subject.value)
        else:
            path = Path(subject)
        if path.is_absolute() or PARENT_DIRECTORY_TOKEN in path.parts:
            raise RuleUsageError(f"finding path must be project-relative: {path}")
        resolved_line: int = line if line is not None else int(getattr(node, "line", 1) or 1)
        resolved_column: int = (
            column if column is not None else int(getattr(node, "column", 1) or 1)
        )
        if resolved_line < 1 or resolved_column < 1:
            raise RuleUsageError("finding line and column must be positive")
        return Finding(
            code=self._rule.code,
            path=path,
            line=resolved_line,
            column=resolved_column,
            message=self._rule.message if message is None else message,
            remediation=self._rule.remediation if remediation is None else remediation,
        )
