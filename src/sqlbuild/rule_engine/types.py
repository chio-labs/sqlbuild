"""Public compiler-rule type declarations."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlbuild.rule_engine.classes.audit_facts import AuditFacts
    from sqlbuild.rule_engine.classes.column_facts import ColumnFacts
    from sqlbuild.rule_engine.classes.contract_facts import ContractFacts
    from sqlbuild.rule_engine.classes.declaration_facts import DeclarationFacts
    from sqlbuild.rule_engine.classes.graph_facts import GraphFacts
    from sqlbuild.rule_engine.classes.model_test_facts import TestFacts
    from sqlbuild.rule_engine.classes.project_facts import ProjectFacts
    from sqlbuild.rule_engine.classes.sql_facts import SqlFacts
    from sqlbuild.rule_engine.models import (
        Finding,
        Model,
        ProjectPath,
        RuleOption,
        SqlNode,
    )

type RuleOptionValue = bool | int | str | tuple[str, ...] | tuple[int, ...]


class RuleSubject(StrEnum):
    """Compiler-owned unit used to invoke and cache one custom rule."""

    MODEL = "model"
    PROJECT = "project"


class RuleContext(Protocol):
    """Stable typed compiler-fact views available to custom rules."""

    @property
    def project(self) -> ProjectFacts: ...

    @property
    def sql(self) -> SqlFacts: ...

    @property
    def graph(self) -> GraphFacts: ...

    @property
    def columns(self) -> ColumnFacts: ...

    @property
    def contracts(self) -> ContractFacts: ...

    @property
    def tests(self) -> TestFacts: ...

    @property
    def audits(self) -> AuditFacts: ...

    @property
    def declarations(self) -> DeclarationFacts: ...

    def option[T](self, option: RuleOption[T]) -> T: ...

    def finding(
        self,
        *,
        subject: Model | ProjectPath | Path | str,
        node: SqlNode | object | None = None,
        line: int | None = None,
        column: int | None = None,
        message: str | None = None,
        remediation: str | None = None,
    ) -> Finding: ...


type RuleCheck = Callable[..., list[Finding]]
