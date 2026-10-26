"""Public compiler-rule type declarations."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlbuild._native import (
        CompiledSqlTest,
        ConstantDeclaration,
        EnumDeclaration,
        Finding,
        InferredColumn,
        Model,
        ProjectPath,
        RuleOption,
        SqlNode,
    )
    from sqlbuild.compiler.compile.types import (
        CompiledAuditView,
        CompiledFunctionView,
        CompiledSeedView,
        CompiledSourceView,
    )
    from sqlbuild.rule_engine.classes.audit_facts import AuditFacts
    from sqlbuild.rule_engine.classes.column_facts import ColumnFacts
    from sqlbuild.rule_engine.classes.contract_facts import ContractFacts
    from sqlbuild.rule_engine.classes.declaration_facts import DeclarationFacts
    from sqlbuild.rule_engine.classes.graph_facts import GraphFacts
    from sqlbuild.rule_engine.classes.model_test_facts import TestFacts
    from sqlbuild.rule_engine.classes.project_facts import ProjectFacts
    from sqlbuild.rule_engine.classes.sql_facts import SqlFacts

type RuleOptionValue = bool | int | str | tuple[str, ...] | tuple[int, ...]
type FactKey = tuple[str, ...]
type CustomRulePlan = dict[str, frozenset[str] | None]


class RuleFactModel(Protocol):
    """One compiled model's facts as a custom-rule host reads them."""

    @property
    def name(self) -> str: ...

    @property
    def relative_path(self) -> Path: ...

    @property
    def key(self) -> object: ...

    @property
    def deps(self) -> tuple[object, ...]: ...

    @property
    def authored_sql(self) -> str: ...

    @property
    def query_sql(self) -> str: ...

    @property
    def declared_columns(self) -> tuple[object, ...]: ...

    @property
    def inferred_columns(self) -> tuple[InferredColumn, ...] | None: ...

    @property
    def enum_declarations(self) -> tuple[EnumDeclaration, ...]: ...

    @property
    def constant_declarations(self) -> tuple[ConstantDeclaration, ...]: ...

    @property
    def enum_type_names(self) -> dict[str, str]: ...

    def config_value(self, name: str) -> object: ...


class RuleFactProject(Protocol):
    """One compiled project's facts as a custom-rule host reads them."""

    @property
    def models(self) -> tuple[RuleFactModel, ...]: ...

    @property
    def effective_target_name(self) -> str | None: ...

    @property
    def sources(self) -> tuple[CompiledSourceView, ...]: ...

    @property
    def seeds(self) -> tuple[CompiledSeedView, ...]: ...

    @property
    def functions(self) -> tuple[CompiledFunctionView, ...]: ...

    @property
    def audits(self) -> tuple[CompiledAuditView, ...]: ...

    @property
    def sql_tests(self) -> tuple[CompiledSqlTest, ...]: ...

    @property
    def public_enums(self) -> dict[str, EnumDeclaration]: ...

    @property
    def public_constants(self) -> dict[str, ConstantDeclaration]: ...


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
