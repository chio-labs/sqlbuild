"""Concrete kata RuleContext for one compiled model and active rule."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject, CompileSqlReference
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import ConstantDeclaration, EnumDeclaration
from sqlbuild.kata_engine._helpers.sql.model_name import parse_model_name
from sqlbuild.kata_engine._helpers.sql.passthrough import is_passthrough_ast
from sqlbuild.kata_engine.constants import PARENT_DIRECTORY_TOKEN
from sqlbuild.kata_engine.exceptions import KataRuleUsageError
from sqlbuild.kata_engine.models import (
    KataConfig,
    KataFault,
    KataRule,
    ModelNameParts,
    RuleOption,
)
from sqlbuild.spec.contracts.models import SchemaColumn


class EvaluationRuleContext:
    """Rule context backed by one compiled model and parsed Polyglot AST."""

    def __init__(
        self,
        *,
        model: CompiledModel,
        ast: Any,
        rule: KataRule,
        config: KataConfig,
        project: CompiledProject,
        project_dir: Path,
        selected_rules: tuple[KataRule, ...],
        is_project_anchor: bool,
    ) -> None:
        self._model: CompiledModel = model
        self._ast: Any = ast
        self._rule: KataRule = rule
        self._config: KataConfig = config
        self._project: CompiledProject = project
        self._project_dir: Path = project_dir
        self._selected_rules: tuple[KataRule, ...] = selected_rules
        self._is_project_anchor: bool = is_project_anchor

    @property
    def model(self) -> CompiledModel:
        return self._model

    @property
    def ast(self) -> Any:
        return self._ast

    @property
    def source(self) -> str:
        return self._model.authored_sql

    @property
    def references(self) -> tuple[CompileSqlReference, ...]:
        return self._model.references

    @property
    def name_parts(self) -> ModelNameParts | None:
        return parse_model_name(self._model.name)

    @property
    def materialization(self) -> str | None:
        value: object = self._model.config.values.get("materialized")
        return value if isinstance(value, str) else None

    @property
    def declared_columns(self) -> tuple[SchemaColumn, ...]:
        return () if self._model.schema_entry is None else self._model.schema_entry.columns

    @property
    def declared_audit_count(self) -> int:
        schema_count: int = 0
        if self._model.schema_entry is not None:
            schema_count = len(self._model.schema_entry.audits)
            schema_count += sum(len(column.audits) for column in self._model.schema_entry.columns)
        compiled_count: int = sum(
            1 for audit in self._project.audits if audit.attached_target_name == self._model.name
        )
        return max(schema_count, compiled_count)

    @property
    def targeting_test_count(self) -> int:
        count: int = 0
        for test in self._project.sql_tests:
            targets_model: bool = any(
                dependency.resource_type == CompiledResourceType.MODEL
                and dependency.name == self._model.name
                for dependency in test.scope_deps
            )
            if targets_model:
                count += 1
        return count

    @property
    def is_passthrough(self) -> bool:
        return len(self._model.references) == 1 and is_passthrough_ast(
            ast=self._ast, source=self._model.query_sql
        )

    @property
    def is_project_anchor(self) -> bool:
        return self._is_project_anchor

    @property
    def project_dir(self) -> Path:
        return self._project_dir

    @property
    def public_enums(self) -> tuple[EnumDeclaration, ...]:
        return tuple(self._project.public_enums.values())

    @property
    def public_constants(self) -> tuple[ConstantDeclaration, ...]:
        return tuple(self._project.public_constants.values())

    @property
    def all_enum_declarations(self) -> tuple[EnumDeclaration, ...]:
        local: list[EnumDeclaration] = []
        for model in self._project.models:
            local.extend(model.enum_declarations)
        return (*self._project.public_enums.values(), *local)

    @property
    def kata_config(self) -> KataConfig:
        return self._config

    @property
    def selected_rules(self) -> tuple[KataRule, ...]:
        return self._selected_rules

    def option[T](self, option: RuleOption[T]) -> T:
        if option not in self._rule.options:
            raise KataRuleUsageError(
                f"option {option.name} is not declared by rule {self._rule.code}"
            )
        value: object = self._config.rule_options.get(self._rule.code, {}).get(
            option.name, option.default
        )
        return cast(T, value)

    def fault(
        self,
        *,
        node: Any | None = None,
        message: str | None = None,
        remediation: str | None = None,
    ) -> KataFault:
        line: int = int(getattr(node, "line", 1) or 1)
        column: int = int(getattr(node, "column", 1) or 1)
        return self._build_fault(
            line=line,
            column=column,
            message=message,
            remediation=remediation,
        )

    def path_fault(
        self, *, message: str | None = None, remediation: str | None = None
    ) -> KataFault:
        return self._build_fault(line=1, column=1, message=message, remediation=remediation)

    def fault_at(
        self,
        *,
        line: int,
        column: int,
        message: str | None = None,
        remediation: str | None = None,
    ) -> KataFault:
        return self._build_fault(
            line=line,
            column=column,
            message=message,
            remediation=remediation,
        )

    def fault_for(
        self,
        *,
        path: Path,
        line: int = 1,
        column: int = 1,
        message: str | None = None,
        remediation: str | None = None,
    ) -> KataFault:
        return KataFault(
            code=self._rule.code,
            path=path,
            line=line,
            column=column,
            message=self._rule.message if message is None else message,
            remediation=self._rule.remediation if remediation is None else remediation,
        )

    def project_read_text(self, *, path: str) -> str:
        target: Path = (self._project_dir / path).resolve()
        if not target.is_relative_to(self._project_dir.resolve()):
            raise KataRuleUsageError(f"project path escapes the repository: {path}")
        try:
            return target.read_text(encoding="utf-8")
        except OSError as error:
            raise KataRuleUsageError(f"could not read project file {path}: {error}") from error

    def project_glob(self, *, pattern: str) -> tuple[Path, ...]:
        configured: Path = Path(pattern)
        if configured.is_absolute() or PARENT_DIRECTORY_TOKEN in configured.parts:
            raise KataRuleUsageError(f"project glob escapes the repository: {pattern}")
        root: Path = self._project_dir.resolve()
        matches: tuple[Path, ...] = tuple(sorted(self._project_dir.glob(pattern)))
        if any(not match.resolve().is_relative_to(root) for match in matches):
            raise KataRuleUsageError(f"project glob escapes the repository: {pattern}")
        return matches

    def _build_fault(
        self,
        *,
        line: int,
        column: int,
        message: str | None,
        remediation: str | None,
    ) -> KataFault:
        return KataFault(
            code=self._rule.code,
            path=Path(self._model.relative_path),
            line=line,
            column=column,
            message=self._rule.message if message is None else message,
            remediation=self._rule.remediation if remediation is None else remediation,
        )
