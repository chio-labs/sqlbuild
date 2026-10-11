"""Compile domain types."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from sqlbuild.sql_values.models import SqlValue

if TYPE_CHECKING:
    from sqlbuild.compiler.compile.models import (
        CompactBatchPreparation,
        CompiledSqlExpansion,
        CompileModelConfig,
        CompileProjectInputs,
        CompileSqlReference,
    )
    from sqlbuild.compiler.discovery.models import (
        ConstantDeclaration,
        DiscoveredSchemaFile,
        DiscoveredSqlModelFile,
        EnumDeclaration,
    )
    from sqlbuild.compiler.scopes.models import UsageRecord
    from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
    from sqlbuild.spec.contracts.models import SchemaModelEntry, SourceLocation


class ModelInput(Protocol):
    """One model's compile input: a native owner view, or a hand-built `CompileModelInput`."""

    @property
    def model_file(self) -> DiscoveredSqlModelFile: ...
    @property
    def config(self) -> CompileModelConfig: ...
    @property
    def query_sql(self) -> str: ...
    @property
    def macro_source_sql(self) -> str: ...
    @property
    def references(self) -> tuple[CompileSqlReference, ...]: ...
    @property
    def schema_entry(self) -> SchemaModelEntry | None: ...
    @property
    def schema_file(self) -> DiscoveredSchemaFile | None: ...
    @property
    def sql_validation_enabled(self) -> bool: ...
    @property
    def rejected_sql_analysis_opt_out(self) -> SourceLocation | None: ...
    @property
    def enum_declarations(self) -> tuple[EnumDeclaration, ...]: ...
    @property
    def constant_declarations(self) -> tuple[ConstantDeclaration, ...]: ...
    @property
    def enum_columns(self) -> dict[str, EnumDeclaration]: ...
    @property
    def macro_deps(self) -> tuple[str, ...]: ...
    @property
    def macro_usages(self) -> tuple[UsageRecord, ...]: ...
    @property
    def declaration_usages(self) -> tuple[UsageRecord, ...]: ...
    @property
    def sql_expansion(self) -> CompiledSqlExpansion | None: ...
    @property
    def lint_expansion(self) -> CompiledSqlExpansion | None: ...


class TypedSqlValueRenderer(Protocol):
    """Adapter rendering operations consumed by authored SQL expansion."""

    adapter_name: str
    sql_lexical_syntax: SqlLexicalSyntax

    def render_typed_scalar(self, *, value: SqlValue) -> str: ...

    def render_typed_value_list(self, *, value: SqlValue) -> str: ...

    def render_typed_array(self, *, value: SqlValue) -> str: ...

    def render_typed_object(self, *, value: SqlValue) -> str: ...


class CompactBatchResponseCallback(Protocol):
    """Keyword-only callback for publishing one native compact response."""

    def __call__(self, *, preparation: CompactBatchPreparation, response: object) -> None: ...


class CompileInputsReadyCallback(Protocol):
    """Invocation-local observer for the completed pre-semantic input snapshot."""

    def __call__(self, *, inputs: CompileProjectInputs) -> None: ...


class AttachedAuditTargetKind(StrEnum):
    MODEL = "model"
    SOURCE = "source"
    SEED = "seed"

    @property
    def resource_type(self) -> CompiledResourceType:
        """Return the compiled resource type of the attached target."""

        return CompiledResourceType(self.value)


class CompileContextKey(StrEnum):
    RUN_ID = "run.id"
    RUN_TARGET = "run.target"
    MODEL_NAME = "model.name"
    MODEL_DATABASE = "model.database"
    MODEL_SCHEMA = "model.schema"
    MODEL_ALIAS = "model.alias"
    DESTINATION_DATABASE = "destination.database"
    DESTINATION_SCHEMA = "destination.schema"
    DESTINATION_TABLE = "destination.table"
    DESTINATION_QUALIFIED = "destination.qualified"


class CompiledResourceType(StrEnum):
    MODEL = "model"
    SOURCE = "source"
    SEED = "seed"
    UDF = "udf"
    TABLE_FN = "table_fn"
    DBT_REF = "dbt_ref"
    AUDIT = "audit"
    SQL_TEST = "sql_test"
    SQL_SCENARIO = "sql_scenario"


class DiagnosticPhase(StrEnum):
    """Phase that produced a compiler diagnostic."""

    COMPILE = "compile"
    CONTRACT = "contract"
    RULE = "rule"
    PLAN = "plan"
    BUILD = "build"
    AUDIT = "audit"
    TEST = "test"
    CONNECTION = "connection"


class DiagnosticSeverity(StrEnum):
    """Severity for a compiler diagnostic."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class FunctionLanguage(StrEnum):
    SQL = "sql"
    PYTHON = "python"


class SqlTestMode(StrEnum):
    MODEL = "model"
    MACRO = "macro"
    UDF = "udf"
    TABLE_FN = "table_fn"


type SqlReferenceScanFailure = tuple[str, int]
