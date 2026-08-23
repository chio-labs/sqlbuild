"""Public kata type-layer declarations."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from sqlbuild.compiler.compile.models import CompiledModel, CompileSqlReference
from sqlbuild.compiler.discovery.models import ConstantDeclaration, EnumDeclaration
from sqlbuild.spec.contracts.models import SchemaColumn

if TYPE_CHECKING:
    from sqlbuild.kata_engine.models import (
        KataConfig,
        KataFault,
        KataRule,
        ModelNameParts,
        RuleOption,
    )

type RuleOptionValue = bool | int | str | tuple[str, ...] | tuple[int, ...]


class RuleContext(Protocol):
    """Public model analysis capabilities available to kata rules."""

    @property
    def model(self) -> CompiledModel: ...

    @property
    def ast(self) -> Any: ...

    @property
    def source(self) -> str: ...

    @property
    def references(self) -> tuple[CompileSqlReference, ...]: ...

    @property
    def name_parts(self) -> ModelNameParts | None: ...

    @property
    def materialization(self) -> str | None: ...

    @property
    def declared_columns(self) -> tuple[SchemaColumn, ...]: ...

    @property
    def declared_audit_count(self) -> int: ...

    @property
    def targeting_test_count(self) -> int: ...

    @property
    def is_passthrough(self) -> bool: ...

    @property
    def is_project_anchor(self) -> bool: ...

    @property
    def project_dir(self) -> Path: ...

    @property
    def public_enums(self) -> tuple[EnumDeclaration, ...]: ...

    @property
    def public_constants(self) -> tuple[ConstantDeclaration, ...]: ...

    @property
    def all_enum_declarations(self) -> tuple[EnumDeclaration, ...]: ...

    @property
    def kata_config(self) -> KataConfig: ...

    @property
    def selected_rules(self) -> tuple[KataRule, ...]: ...

    def option[T](self, option: RuleOption[T]) -> T: ...

    def fault(
        self,
        *,
        node: Any | None = None,
        message: str | None = None,
        remediation: str | None = None,
    ) -> KataFault: ...

    def path_fault(
        self, *, message: str | None = None, remediation: str | None = None
    ) -> KataFault: ...

    def fault_at(
        self,
        *,
        line: int,
        column: int,
        message: str | None = None,
        remediation: str | None = None,
    ) -> KataFault: ...

    def fault_for(
        self,
        *,
        path: Path,
        line: int = 1,
        column: int = 1,
        message: str | None = None,
        remediation: str | None = None,
    ) -> KataFault: ...

    def project_read_text(self, *, path: str) -> str: ...

    def project_glob(self, *, pattern: str) -> tuple[Path, ...]: ...


class KataCheck(Protocol):
    """One kata rule implementation."""

    def __call__(self, *, model: CompiledModel, ctx: RuleContext) -> list[KataFault]: ...
