"""Compile domain types."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

from sqlbuild.sql_values.models import SqlValue

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    import sqlbuild._native as _native
    from sqlbuild.compiler.compile.models import (
        CompactBatchPreparation,
        CompileAuditInput,
        CompiledAudit,
        CompiledFunction,
        CompiledLineageColumnFact,
        CompiledObjectKey,
        CompiledRelationLocation,
        CompiledSeed,
        CompiledSource,
        CompiledSqlExpansion,
        CompiledSqlScenario,
        CompiledSqlTest,
        CompileModelConfig,
        CompilerDiagnostic,
        CompileSeedInput,
        CompileSourceInput,
        CompileSqlFunctionInput,
        CompileSqlReference,
        CompileSqlScenarioInput,
        CompileSqlTestInput,
        DeclarationScopeBuild,
        DynamicColumnContractProof,
        InferredColumn,
        LoadedMacro,
        MacroContext,
    )
    from sqlbuild.compiler.discovery.models import (
        ConstantDeclaration,
        DiscoveredHookFunction,
        DiscoveredLoaderFunction,
        DiscoveredMaterializationFile,
        DiscoveredProjectInputs,
        DiscoveredSchemaFile,
        DiscoveredSqlHookFile,
        DiscoveredSqlModelFile,
        EnumDeclaration,
    )
    from sqlbuild.compiler.references.models import LiteralSqlRelation
    from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver
    from sqlbuild.compiler.scopes.models import ScopeIndex, UsageRecord
    from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
    from sqlbuild.spec.contracts.models import (
        LocalConfig,
        ProjectConfig,
        ScenarioConfig,
        SchemaModelEntry,
        SettingsConfig,
        SourceLocation,
        TargetConfig,
    )


class CompileInputsView(Protocol):
    """A compile's attached inputs: a native owner view, or hand-built `CompileProjectInputs`."""

    @property
    def project_config(self) -> ProjectConfig: ...
    @property
    def local_config(self) -> LocalConfig: ...
    @property
    def discovered_inputs(self) -> DiscoveredProjectInputs: ...
    @property
    def sql_lexical_syntax(self) -> SqlLexicalSyntax: ...
    @property
    def run_id(self) -> str: ...
    @property
    def effective_target_name(self) -> str | None: ...
    @property
    def effective_target(self) -> TargetConfig | None: ...
    @property
    def compile_cache_dir(self) -> Path | None: ...
    @property
    def effective_connection(self) -> dict[str, object]: ...
    @property
    def effective_settings(self) -> SettingsConfig: ...
    @property
    def no_sql_validation(self) -> bool: ...
    @property
    def effective_vars(self) -> dict[str, object]: ...
    @property
    def macro_context(self) -> MacroContext | None: ...
    @property
    def loaded_macros(self) -> dict[str, LoadedMacro]: ...
    @property
    def public_enums(self) -> dict[str, EnumDeclaration]: ...
    @property
    def public_constants(self) -> dict[str, ConstantDeclaration]: ...
    @property
    def model_inputs(self) -> tuple[ModelInput, ...]: ...
    @property
    def seed_inputs(self) -> tuple[CompileSeedInput, ...]: ...
    @property
    def source_inputs(self) -> tuple[CompileSourceInput, ...]: ...
    @property
    def sql_function_inputs(self) -> tuple[CompileSqlFunctionInput, ...]: ...
    @property
    def test_inputs(self) -> tuple[CompileSqlTestInput, ...]: ...
    @property
    def scenario_inputs(self) -> tuple[CompileSqlScenarioInput, ...]: ...
    @property
    def audit_inputs(self) -> tuple[CompileAuditInput, ...]: ...
    @property
    def diagnostics(self) -> tuple[CompilerDiagnostic, ...]: ...
    @property
    def external_sql_reference_resolver(self) -> ExternalSqlReferenceResolver | None: ...
    @property
    def scope_index(self) -> ScopeIndex: ...
    @property
    def declaration_scope(self) -> DeclarationScopeBuild | None: ...
    @property
    def native_project(self) -> _native.NativeCompiledProject | None: ...


class CompiledProjectView(Protocol):
    """One compiled project: a native owner view, or a hand-built `CompiledProject`."""

    @property
    def run_id(self) -> str: ...
    @property
    def effective_target_name(self) -> str | None: ...
    @property
    def effective_connection(self) -> dict[str, object]: ...
    @property
    def effective_vars(self) -> dict[str, object]: ...
    @property
    def binding_catalog(self) -> Any | None: ...
    @property
    def effective_target_database(self) -> str | None: ...
    @property
    def effective_target_schema(self) -> str | None: ...
    @property
    def sql_analysis_dialect(self) -> str | None: ...
    @property
    def sql_lexical_syntax(self) -> SqlLexicalSyntax: ...
    @property
    def compile_cache_dir(self) -> Path | None: ...
    @property
    def settings(self) -> SettingsConfig: ...
    @property
    def scenario(self) -> ScenarioConfig: ...
    @property
    def models(self) -> tuple[CompiledModelView, ...]: ...
    @property
    def sources(self) -> tuple[CompiledSource, ...]: ...
    @property
    def seeds(self) -> tuple[CompiledSeed, ...]: ...
    @property
    def functions(self) -> tuple[CompiledFunction, ...]: ...
    @property
    def audits(self) -> tuple[CompiledAudit, ...]: ...
    @property
    def sql_tests(self) -> tuple[CompiledSqlTest, ...]: ...
    @property
    def sql_scenarios(self) -> tuple[CompiledSqlScenario, ...]: ...
    @property
    def loader_functions(self) -> tuple[DiscoveredLoaderFunction, ...]: ...
    @property
    def hook_functions(self) -> tuple[DiscoveredHookFunction, ...]: ...
    @property
    def enforce_explicit_references(self) -> bool: ...
    @property
    def sql_hook_files(self) -> tuple[DiscoveredSqlHookFile, ...]: ...
    @property
    def materialization_files(self) -> tuple[DiscoveredMaterializationFile, ...]: ...
    @property
    def public_enums(self) -> dict[str, EnumDeclaration]: ...
    @property
    def public_constants(self) -> dict[str, ConstantDeclaration]: ...
    @property
    def loaded_macros(self) -> dict[str, LoadedMacro]: ...
    @property
    def diagnostics(self) -> tuple[CompilerDiagnostic, ...]: ...
    @property
    def unmatched_literal_sql_relations(self) -> tuple[LiteralSqlRelation, ...]: ...
    @property
    def external_sql_reference_resolver(self) -> ExternalSqlReferenceResolver | None: ...
    @property
    def scope_index(self) -> ScopeIndex: ...
    @property
    def sql_expansions(self) -> dict[Path, CompiledSqlExpansion]: ...
    @property
    def native_session(self) -> Any | None: ...
    @property
    def native_project(self) -> _native.NativeCompiledProject | None: ...
    @property
    def lineage_graph(self) -> _native.NativeProjectGraph: ...


class CompiledModelView(Protocol):
    """One compiled model: a native owner view, or a hand-built `CompiledModel`."""

    @property
    def key(self) -> CompiledObjectKey: ...
    @property
    def deps(self) -> tuple[CompiledObjectKey, ...]: ...
    @property
    def name(self) -> str: ...
    @property
    def relative_path(self) -> Path: ...
    @property
    def query_sql(self) -> str: ...
    @property
    def config(self) -> CompileModelConfig: ...
    @property
    def destination(self) -> CompiledRelationLocation: ...
    @property
    def references(self) -> tuple[CompileSqlReference, ...]: ...
    @property
    def schema_entry(self) -> SchemaModelEntry | None: ...
    @property
    def inferred_columns(self) -> tuple[InferredColumn, ...] | None: ...
    @property
    def fast_lineage_columns(self) -> Sequence[CompiledLineageColumnFact] | None: ...
    @property
    def fast_lineage_has_star(self) -> bool: ...
    @property
    def fast_lineage_star_resolved(self) -> bool: ...
    @property
    def authored_sql(self) -> str: ...
    @property
    def authored_query_sql(self) -> str: ...
    @property
    def output_column_locations(self) -> dict[str, SourceLocation]: ...
    @property
    def extract_implicit_alias_columns(self) -> bool: ...
    @property
    def macro_deps(self) -> tuple[str, ...]: ...
    @property
    def enum_declarations(self) -> tuple[EnumDeclaration, ...]: ...
    @property
    def constant_declarations(self) -> tuple[ConstantDeclaration, ...]: ...
    @property
    def enum_columns(self) -> dict[str, EnumDeclaration]: ...
    @property
    def binding_diagnostics(self) -> tuple[CompilerDiagnostic, ...]: ...
    @property
    def binding_validated(self) -> bool: ...
    @property
    def dynamic_column_contract(self) -> DynamicColumnContractProof | None: ...
    @property
    def unchecked_output_columns(self) -> frozenset[str]: ...
    @property
    def rejected_sql_analysis_opt_out(self) -> SourceLocation | None: ...
    @property
    def reference_rows(self) -> list[tuple[str, str, str | None, int | None]]: ...
    @property
    def key_row(self) -> tuple[str, str]: ...
    @property
    def dep_rows(self) -> list[tuple[str, str]]: ...
    @property
    def destination_row(self) -> tuple[str | None, str | None, str]: ...
    @property
    def inferred_rows(self) -> list[tuple[str, str | None, str]] | None: ...
    @property
    def schema_column_rows(self) -> list[tuple[str, str | None]] | None: ...
    @property
    def has_dynamic_columns(self) -> bool: ...
    @property
    def output_column_count(self) -> int: ...


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
    @property
    def reference_rows(self) -> list[tuple[str, str, str | None, int | None]]: ...
    @property
    def attached_schema_name(self) -> str | None: ...


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

    def __call__(self, *, inputs: CompileInputsView) -> None: ...


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
