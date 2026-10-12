"""Private SQLBuild native engine bindings."""

from collections.abc import Callable, Hashable, Mapping, Sequence, Set
from pathlib import Path, PurePath
from typing import Any, Literal, TypedDict, overload

from _typeshed import SupportsRichComparison

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.cli.commands.classes.prepared_compile_artifacts import PreparedCompileArtifacts
from sqlbuild.cli.commands.types import CompileLineageMode
from sqlbuild.cli.compile.models import CompileAnalysis
from sqlbuild.cli.compile_reuse.models import CompileReuseAttempt
from sqlbuild.cli.entry.models import CompileCommandRequest, CompileProfileFlags
from sqlbuild.compiler.auditing.models import MeasurementContract, MeasurementThresholds
from sqlbuild.compiler.auditing.types import AuditEvaluationMode, AuditSeverity
from sqlbuild.compiler.compile.models import (
    CompileAdapterContext,
    CompileAnalysisSelection,
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
    FunctionArgument,
    FunctionReturnColumn,
    InferredColumn,
    LoadedMacro,
    MacroContext,
    StaticMacroExport,
    StaticMacroFault,
)
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
    CompiledModelView,
    CompiledProjectView,
    CompileInputsView,
    FunctionLanguage,
)
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredAdapterFile,
    DiscoveredAuditBlock,
    DiscoveredAuditFile,
    DiscoveredConstantFile,
    DiscoveredEnumFile,
    DiscoveredHookFunction,
    DiscoveredLoaderFunction,
    DiscoveredMacroFile,
    DiscoveredMaterializationFile,
    DiscoveredModelSchemaFile,
    DiscoveredProjectInputs,
    DiscoveredPythonFunctionFile,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
    DiscoveredSqlFunctionFile,
    DiscoveredSqlHookFile,
    DiscoveredSqlScenarioFile,
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestFile,
    DiscoveryFileFault,
    EnumDeclaration,
    ModelSchemaDeclaration,
    TolerantScopeDiscovery,
)
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from sqlbuild.compiler.lineage.models import (
    ColumnLineageEdge,
    DirectSemanticColumnUse,
    ModelColumnLineage,
    QualifiedLineageColumn,
)
from sqlbuild.compiler.lineage.types import ColumnLineageMode, InferredNullability
from sqlbuild.compiler.pipeline.models import (
    CompiledProjectPhaseResult,
    CompilePipelineOptions,
    CompilePipelineResult,
    ProjectGraph,
)
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph, PythonNodeIdentity
from sqlbuild.compiler.references.models import LiteralSqlRelation
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver
from sqlbuild.compiler.scopes.models import (
    DeclarationExplanation,
    DeclarationIdentity,
    DeclarationRecord,
    DeclarationVisibility,
    MovePreview,
    ResourceIdentity,
    ScopeBrowseResult,
    ScopeDiagnostic,
    ScopeIndex,
    ScopeListResult,
    ScopeLookup,
    ScopeReport,
    ScopeReportFilters,
    ScopeTargetQuery,
    UsageRecord,
    VisibilityResolution,
)
from sqlbuild.compiler.scopes.types import JsonValue, ScopeQueryTarget
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from sqlbuild.compiler.sql_test_glue.models import (
    NativeSqlTestAssemblyRequest,
    NativeSqlTestChainRequest,
    NativeSqlTestPlanningRequest,
)
from sqlbuild.compiler.sql_test_glue.types import NativeSqlTestAssemblyRow, NativeSqlTestPlanRow
from sqlbuild.lint.types import RelationKeyRow
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.runtime.contracts.models import ConnectionHooks
from sqlbuild.spec.contracts.models import (
    DefaultsConfig,
    LocalConfig,
    ProjectConfig,
    ScenarioConfig,
    SchemaModelEntry,
    SchemaSeedEntry,
    SettingsConfig,
    SourceEntry,
    SourceLocation,
    TargetConfig,
)

BUILD_IDENTITY: str

class NativeCompilerError(RuntimeError):
    """An internal native compiler failure: a panic or a broken native invariant."""

class LintPreparationRequest(TypedDict):
    expanded: str
    before_expansion: str
    prior_sites: list[int]
    dialect: str

def analyze_column_references_json(request_json: str) -> str: ...
def catalogue_json() -> str: ...

class NativeRulesRequest:
    """A natively built rules request held until it is evaluated once."""

def build_rules_request(
    project: dict[str, object],
    models: tuple[NativeCompiledProject, list[str]],
    sql_tests: list[tuple[object, ...]],
    scenarios: list[tuple[object, ...]],
) -> NativeRulesRequest: ...
def evaluate_rules_request(
    request: NativeRulesRequest,
) -> tuple[
    list[tuple[bool, str, str, int, int, str, str]], list[str], int, int, int, int, bool
]: ...
def emit_orjson_report(report: object) -> str: ...
def emit_json_report(report: object) -> str: ...

type _GraphKey = tuple[str, str]
type _GraphEdges = list[tuple[_GraphKey, list[_GraphKey]]]
type _GraphIndexes = tuple[
    list[tuple[str, _GraphKey]],
    _GraphEdges,
    _GraphEdges,
    list[tuple[str, list[_GraphKey]]],
    list[tuple[_GraphKey, str]],
]
type _SelectorFailure = tuple[str, str, str | None]
type _SelectorKeys = tuple[list[_GraphKey] | None, _SelectorFailure | None]

class NativeModelInput:
    @property
    def reference_rows(self) -> list[tuple[str, str, str | None, int | None]]: ...
    @property
    def attached_schema_name(self) -> str | None: ...
    @property
    def relation_key_row(self) -> RelationKeyRow: ...
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
    def compiled_model(
        self,
        arguments: tuple[
            list[tuple[str, str]],
            tuple[NativeModelAnalysisSession, int] | None,
            list[tuple[str, str | None, str]] | None,
            tuple[
                bool,
                list[tuple[str, str | None, str]],
                list[tuple[str, str | None]],
                list[str],
                str | None,
                bool,
            ]
            | None,
            list[str],
        ],
    ) -> NativeCompiledModel: ...

class NativeCompiledModel:
    @property
    def reference_rows(self) -> list[tuple[str, str, str | None, int | None]]: ...
    @property
    def relation_key_row(self) -> RelationKeyRow: ...
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
    def with_binding_diagnostics(
        self, diagnostics: tuple[CompilerDiagnostic, ...]
    ) -> NativeCompiledModel: ...
    def with_type_recovery(
        self, diagnostics: tuple[CompilerDiagnostic, ...], poisoned: list[str]
    ) -> NativeCompiledModel: ...
    def with_target_defaults(
        self, defaults: tuple[str | None, str | None], render: Callable[..., str | None]
    ) -> NativeCompiledModel: ...

class NativeInputsView:
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
    def model_inputs(self) -> tuple[NativeModelInput, ...]: ...
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
    def native_project(self) -> NativeCompiledProject | None: ...
    def with_changes(self, **changes: object) -> NativeInputsView: ...
    def fields(self) -> dict[str, Any]: ...

class NativeSeedInput:
    @property
    def seed_file(self) -> DiscoveredSeedFile: ...
    @property
    def schema_entry(self) -> SchemaSeedEntry: ...
    @property
    def schema_file(self) -> DiscoveredSchemaFile: ...

class NativeCompiledSeed:
    @property
    def key(self) -> CompiledObjectKey: ...
    @property
    def deps(self) -> tuple[CompiledObjectKey, ...]: ...
    @property
    def name(self) -> str: ...
    @property
    def seed_file(self) -> DiscoveredSeedFile: ...
    @property
    def schema_entry(self) -> SchemaSeedEntry: ...
    @property
    def schema_file(self) -> DiscoveredSchemaFile: ...
    @property
    def destination(self) -> CompiledRelationLocation: ...
    @property
    def external(self) -> bool: ...
    def with_target_defaults(
        self,
        defaults: tuple[str | None, str | None],
        render: Callable[..., str | None],
    ) -> NativeCompiledSeed: ...

class NativeSourceInput:
    @property
    def source_entry(self) -> SourceEntry: ...
    @property
    def source_file(self) -> DiscoveredSourceFile: ...
    @property
    def declaration_usages(self) -> tuple[UsageRecord, ...]: ...
    @property
    def assembly_row(self) -> tuple[str, bool, str | None, str | None]: ...

class NativeCompiledSource:
    @property
    def key(self) -> CompiledObjectKey: ...
    @property
    def deps(self) -> tuple[CompiledObjectKey, ...]: ...
    @property
    def name(self) -> str: ...
    @property
    def source_entry(self) -> SourceEntry: ...
    @property
    def source_file(self) -> DiscoveredSourceFile: ...

class NativeFunctionInput:
    @property
    def function_file(self) -> DiscoveredSqlFunctionFile | DiscoveredPythonFunctionFile: ...
    @property
    def name(self) -> str: ...
    @property
    def arguments(self) -> tuple[FunctionArgument, ...]: ...
    @property
    def returns(self) -> str: ...
    @property
    def body_sql(self) -> str: ...
    @property
    def return_columns(self) -> tuple[FunctionReturnColumn, ...]: ...
    @property
    def references(self) -> tuple[CompileSqlReference, ...]: ...
    @property
    def language(self) -> FunctionLanguage: ...
    @property
    def runtime_version(self) -> str | None: ...
    @property
    def entry_point(self) -> str | None: ...
    @property
    def packages(self) -> tuple[str, ...]: ...
    @property
    def tags(self) -> tuple[str, ...]: ...
    @property
    def description(self) -> str | None: ...
    @property
    def database(self) -> str | None: ...
    @property
    def schema(self) -> str | None: ...
    @property
    def logical_database(self) -> str | None: ...
    @property
    def logical_schema(self) -> str | None: ...
    @property
    def fingerprint_database(self) -> str | None: ...
    @property
    def fingerprint_schema(self) -> str | None: ...
    @property
    def fingerprint_logical_database(self) -> str | None: ...
    @property
    def fingerprint_logical_schema(self) -> str | None: ...
    @property
    def declaration_usages(self) -> tuple[UsageRecord, ...]: ...
    @property
    def assembly_row(
        self,
    ) -> tuple[str, str, list[str], list[tuple[str, str, str | None]]]: ...

class NativeCompiledFunction:
    @property
    def key(self) -> CompiledObjectKey: ...
    @property
    def deps(self) -> tuple[CompiledObjectKey, ...]: ...
    @property
    def name(self) -> str: ...
    @property
    def arguments(self) -> tuple[FunctionArgument, ...]: ...
    @property
    def returns(self) -> str: ...
    @property
    def body_sql(self) -> str: ...
    @property
    def return_columns(self) -> tuple[FunctionReturnColumn, ...]: ...
    @property
    def references(self) -> tuple[CompileSqlReference, ...]: ...
    @property
    def language(self) -> FunctionLanguage: ...
    @property
    def runtime_version(self) -> str | None: ...
    @property
    def entry_point(self) -> str | None: ...
    @property
    def packages(self) -> tuple[str, ...]: ...
    @property
    def tags(self) -> tuple[str, ...]: ...
    @property
    def description(self) -> str | None: ...
    @property
    def relative_path(self) -> Path: ...
    @property
    def source_file_path(self) -> Path | None: ...
    @property
    def destination(self) -> CompiledRelationLocation: ...
    @property
    def fingerprint_destination(self) -> CompiledRelationLocation: ...
    def with_target_defaults(
        self,
        defaults: tuple[str | None, str | None],
        render: Callable[..., str | None],
        python_functions_inherit_default_namespace: bool,
    ) -> NativeCompiledFunction: ...

class NativeAuditInput:
    @property
    def audit_file(self) -> DiscoveredAuditFile: ...
    @property
    def audit_block(self) -> DiscoveredAuditBlock: ...
    @property
    def sql_body(self) -> str: ...
    @property
    def evaluation_mode(self) -> AuditEvaluationMode: ...
    @property
    def measurement_contract(self) -> MeasurementContract | None: ...
    @property
    def thresholds(self) -> MeasurementThresholds | None: ...
    @property
    def minimum_samples(self) -> int | None: ...
    @property
    def measure_sql(self) -> str | None: ...
    @property
    def evidence_sql(self) -> str | None: ...
    @property
    def evidence_limit(self) -> int | None: ...
    @property
    def references(self) -> tuple[CompileSqlReference, ...]: ...
    @property
    def attached_target_kind(self) -> AttachedAuditTargetKind | None: ...
    @property
    def attached_target_name(self) -> str | None: ...
    @property
    def attached_column_name(self) -> str | None: ...
    @property
    def severity(self) -> AuditSeverity | None: ...
    @property
    def run_scope(self) -> str | None: ...
    @property
    def always_run(self) -> bool: ...
    @property
    def description(self) -> str | None: ...
    @property
    def declaration_usages(self) -> tuple[UsageRecord, ...]: ...
    @property
    def name(self) -> str | None: ...
    @property
    def assembly_row(
        self,
    ) -> tuple[list[tuple[str, str, str | None]], tuple[str, str] | None]: ...

class NativeCompiledAudit:
    @property
    def key(self) -> CompiledObjectKey: ...
    @property
    def scope_deps(self) -> tuple[CompiledObjectKey, ...]: ...
    @property
    def name(self) -> str: ...
    @property
    def definition_name(self) -> str: ...
    @property
    def audit_file(self) -> DiscoveredAuditFile: ...
    @property
    def audit_block(self) -> DiscoveredAuditBlock: ...
    @property
    def sql_body(self) -> str: ...
    @property
    def evaluation_mode(self) -> AuditEvaluationMode: ...
    @property
    def measurement_contract(self) -> MeasurementContract | None: ...
    @property
    def thresholds(self) -> MeasurementThresholds | None: ...
    @property
    def minimum_samples(self) -> int | None: ...
    @property
    def measure_sql(self) -> str | None: ...
    @property
    def evidence_sql(self) -> str | None: ...
    @property
    def evidence_limit(self) -> int | None: ...
    @property
    def references(self) -> tuple[CompileSqlReference, ...]: ...
    @property
    def attached_target_kind(self) -> AttachedAuditTargetKind | None: ...
    @property
    def attached_target_name(self) -> str | None: ...
    @property
    def attached_column_name(self) -> str | None: ...
    @property
    def severity(self) -> AuditSeverity | None: ...
    @property
    def run_scope(self) -> str | None: ...
    @property
    def always_run(self) -> bool: ...
    @property
    def description(self) -> str | None: ...

class NativeProjectView:
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
    def native_project(self) -> NativeCompiledProject | None: ...
    @property
    def lineage_graph(self) -> NativeProjectGraph: ...
    def with_changes(self, **changes: object) -> NativeProjectView: ...
    def fields(self, include_sql_expansions: bool = True) -> dict[str, Any]: ...

class NativeCompiledProject:
    def __init__(self) -> None: ...
    def record_model(self, model: tuple[object, ...]) -> None: ...
    def record_model_analysis(
        self,
        name: str,
        columns: tuple[bool, list[tuple[str, str | None]], list[bool], bool, list[str]],
        dynamic_proof: tuple[
            bool,
            bool,
            list[tuple[str, str | None]],
            str | None,
            list[tuple[str, str | None]],
        ]
        | None,
    ) -> bool: ...
    def record_view_analyses(self, views: list[NativeCompiledModel]) -> int: ...
    def model_names(self) -> list[str]: ...
    def project_view(self, fields: dict[str, object]) -> NativeProjectView: ...
    def inputs_view(self, fields: dict[str, object]) -> NativeInputsView: ...
    def attach_seeds(
        self,
        declarations: list[tuple[SchemaSeedEntry, DiscoveredSchemaFile]],
        seed_files: list[DiscoveredSeedFile],
        compile_error: type[Exception],
    ) -> list[NativeSeedInput]: ...
    def record_seed_namespaces(
        self, namespaces: list[tuple[str | None, str | None, str | None, str | None]]
    ) -> None: ...
    def compiled_seed(self, index: int) -> NativeCompiledSeed: ...
    def attach_sources(
        self,
        rows: list[tuple[str, DiscoveredSourceFile, SourceEntry]],
        settings: tuple[str | None, bool, object],
    ) -> list[NativeSourceInput]: ...
    def record_source_namespaces(
        self, namespaces: list[tuple[str | None, str | None] | None]
    ) -> None: ...
    def compiled_source(self, index: int) -> NativeCompiledSource: ...
    def attach_functions(
        self,
        rows: tuple[list[tuple[object, ...]], list[tuple[object, ...]]],
        settings: tuple[
            str,
            bool,
            tuple[str | None, str | None],
            tuple[str | None, str | None] | None,
            bool,
            object,
        ],
    ) -> list[NativeFunctionInput]: ...
    def record_function_deps(self, deps: list[list[tuple[str, str]]]) -> None: ...
    def compiled_function(self, index: int) -> NativeCompiledFunction: ...
    def resource_diagnostics(
        self, settings: dict[str, object]
    ) -> tuple[list[CompilerDiagnostic], list[CompilerDiagnostic], list[CompilerDiagnostic]]: ...
    def attach_sql_tests(
        self,
        files: list[tuple[object, ...]],
        scenarios: list[tuple[object, ...]],
        settings: dict[str, object],
    ) -> tuple[list[CompileSqlTestInput], list[CompileSqlScenarioInput]]: ...
    def attach_audits(
        self, files: list[tuple[object, ...]], settings: dict[str, object]
    ) -> tuple[list[NativeAuditInput], list[CompilerDiagnostic]]: ...
    def record_audit_scope_deps(self, deps: list[list[tuple[str, str]]]) -> None: ...
    def compiled_audit(self, index: int) -> NativeCompiledAudit: ...
    def graph_builds(self) -> int: ...
    def __eq__(self, other: object) -> bool: ...

class NativeMacroExpansion:
    def __init__(
        self,
        file_path: object,
        state: tuple[object, object, object, object, object],
        enforce_explicit: bool,
        classes: dict[str, object],
    ) -> None: ...
    def expand(
        self, sql: str, bridge: object
    ) -> tuple[
        str,
        list[tuple[int, int, int, int]],
        list[tuple[str, str]],
        list[Any],
        list[Any],
    ]: ...
    def render_relation(self, reference: object) -> str: ...
    def declaration_read(self, kind: str, name: str) -> None: ...
    def block_memo(self) -> None: ...

class NativeModelLoop:
    def __init__(
        self,
        checks: tuple[object, dict[str, object], dict[str, object]],
        syntax: dict[str, object],
        reserved_markers: list[str],
        settings: tuple[tuple[bool, bool, bool, bool], str],
    ) -> None: ...
    def run(
        self,
        project: NativeCompiledProject,
        host: object,
        model_files: list[DiscoveredSqlModelFile],
    ) -> list[NativeModelInput]: ...

def relation_key_row(
    kind: str, name: str, values: dict[str, object], entry: object
) -> RelationKeyRow: ...
def declared_relation_keys(rows: list[RelationKeyRow]) -> dict[str, list[list[str]]]: ...
def build_dag_json(
    *, graph: ProjectGraph, project_name: str, python_graph: PythonNodeGraph | None = None
) -> str: ...

class _ManifestFacts(TypedDict):
    project_name: str
    adapter_type: str
    generated_at: str
    hook_identities: Mapping[str, PythonNodeIdentity]

class NativeManifest:
    def contents(self) -> bytes: ...

def build_manifest(
    *,
    project: CompiledProjectView,
    plan_output: PlanOutput | None,
    graph: NativeProjectGraph,
    facts: _ManifestFacts,
) -> NativeManifest: ...

class NativeProjectGraph:
    @staticmethod
    def from_resources(
        resources: list[tuple[_GraphKey, list[_GraphKey], list[str], str | None]],
    ) -> NativeProjectGraph: ...
    @staticmethod
    def from_indexes(indexes: _GraphIndexes) -> NativeProjectGraph: ...
    def indexes(self) -> _GraphIndexes: ...
    def upstream(self, key: _GraphKey) -> list[_GraphKey]: ...
    def downstream(self, key: _GraphKey) -> list[_GraphKey]: ...
    def keys(self) -> list[_GraphKey]: ...
    def names(self) -> list[tuple[str, _GraphKey]]: ...
    def edges(self) -> list[tuple[_GraphKey, _GraphKey]]: ...
    def model_layer_count(self) -> int: ...
    def unique_id_maps(
        self, project_name: str, prefixes: dict[str, str]
    ) -> tuple[list[tuple[str, list[str]]], list[tuple[str, list[str]]]]: ...
    def resolve(self, select: list[str], exclude: list[str]) -> _SelectorKeys: ...
    def tokens(self, selectors: list[str]) -> _SelectorKeys: ...
    def matched(self, kind: str, value: str) -> _SelectorKeys: ...
    def build_resources(
        self, selected: list[_GraphKey], include: tuple[bool, bool, bool]
    ) -> list[_GraphKey]: ...

def parse_project_selector(
    raw: str,
) -> tuple[tuple[str, str, str, bool, bool] | None, _SelectorFailure | None]: ...
def project_selector_name_help(value: str, candidates: list[str]) -> str | None: ...

class NativeReuseAttempt:
    def outcome(self) -> str: ...
    def store_path(self) -> str: ...
    def replay_failed(self) -> bool: ...
    def snapshot_paths(self) -> int: ...
    def pending_digest_bytes(self) -> int: ...
    def replay(self, timings: list[tuple[str, int]]) -> tuple[str, list[str], int] | None: ...
    def digested_files(self) -> int: ...
    def launch_identity(self) -> tuple[str, dict[str, str], list[str]]: ...
    def record(self, record: dict[str, object]) -> tuple[str, int]: ...

def check_compile_reuse(check: dict[str, object]) -> NativeReuseAttempt: ...
def artifact_digest(contents: bytes) -> str: ...
def write_compiled_artifacts(
    files: list[tuple[Path, bytes]], check_existing: bool
) -> tuple[int, int]: ...
def staged_artifact_files(staged_dir: Path) -> list[str]: ...
def remove_stale_artifacts(compiled_dir: Path, managed: list[str]) -> int: ...
def publish_staged_artifacts(
    staged_dir: Path, compiled_dir: Path, expected: list[str]
) -> tuple[str, list[tuple[str, str]]]: ...
def finalize_rule_findings_rows(
    request: dict[str, object],
) -> list[tuple[bool, str, str, int, int, str, str]]: ...
def run_custom_host_json(spec_json: str) -> str: ...
def format_sql_json(request_json: str) -> str: ...
def format_sql_batch_json(request_json: str) -> str: ...
def query_fingerprint(sql: str, dialect: str) -> str: ...
def lint_sql_json(request_json: str) -> str: ...
def lint_sql_batch_json(request_json: str) -> str: ...
def prepare_lint_sql(
    request: LintPreparationRequest,
) -> tuple[str, list[tuple[str, int, int, int, int, str]], list[str]] | None: ...
def prepare_lint_sql_batch(
    requests: list[LintPreparationRequest],
) -> list[tuple[bool, tuple[str, list[tuple[str, int, int, int, int, str]], list[str]] | None]]: ...
def lint_backtick_identifiers(dialect: str) -> bool: ...
def load_config_json(project_dir: str) -> str: ...
def selected_codes_json(request_json: str) -> str: ...
def render_owned_skill(content: str, input_fingerprint: str) -> str: ...
def skill_freshness(content: str | None, input_fingerprint: str) -> str: ...
def match_model_headers(contents: list[str]) -> list[tuple[int, int, int] | None]: ...
def parse_model_headers(
    headers: list[str],
) -> list[tuple[dict[str, object] | None, list[tuple[str, int, int]] | None, str | None]]: ...
def tokenize_model_header(header: str) -> list[tuple[int, str, int]]: ...
def model_output_columns(
    contents: str, implicit_aliases: bool
) -> list[tuple[str, int, int, int, int]]: ...
def model_header_column_locations(
    contents: str, header: str, header_start: int
) -> tuple[list[tuple[str, int, int, int, int]] | None, str | None]: ...
def model_header_failure(
    error: str, header: str, header_line: int | None
) -> tuple[str, str | None, int | None]: ...

class NativeProjectTree:
    def __init__(self, project_dir: str) -> None: ...

class DiscoveredSqlModelFile:
    """A discovered SQL model file and its raw contents."""

    def __init__(
        self,
        file_path: Path,
        relative_path: Path,
        contents: str,
        header_values: dict[str, object],
        header_column_locations: dict[str, SourceLocation],
        output_column_locations: dict[str, SourceLocation],
        query_sql: str,
        enum_declarations: tuple[EnumDeclaration, ...] = (),
        constant_declarations: tuple[ConstantDeclaration, ...] = (),
        extract_implicit_alias_columns: bool = True,
    ) -> None: ...
    @property
    def file_path(self) -> Path: ...
    @property
    def relative_path(self) -> Path: ...
    @property
    def contents(self) -> str: ...
    @property
    def header_values(self) -> dict[str, object]: ...
    @property
    def header_column_locations(self) -> dict[str, SourceLocation]: ...
    @property
    def output_column_locations(self) -> dict[str, SourceLocation]: ...
    @property
    def query_sql(self) -> str: ...
    def with_text(self, contents: str, query_sql: str) -> DiscoveredSqlModelFile: ...
    @property
    def enum_declarations(self) -> tuple[EnumDeclaration, ...]: ...
    @property
    def constant_declarations(self) -> tuple[ConstantDeclaration, ...]: ...
    @property
    def extract_implicit_alias_columns(self) -> bool: ...

def parse_schema_document(
    loaded: object, path: str, classes: dict[str, object]
) -> tuple[SchemaSeedEntry, ...]: ...
def parse_sources_document(
    loaded: object, path: str, classes: dict[str, object]
) -> tuple[SourceEntry, ...]: ...
def analyze_compile_project(
    *,
    project_dir: Path,
    no_sql_validation: bool,
    selected_target: str | None,
    lineage_mode: CompileLineageMode,
    cli_vars: dict[str, object] | None,
    profile_flags: CompileProfileFlags,
    analysis_selection: CompileAnalysisSelection,
    status: TransientStatusReporter | None,
    prepared_artifacts: PreparedCompileArtifacts | None = None,
) -> CompileAnalysis: ...
def build_compiled_project(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    selected_target: str | None = None,
    no_sql_validation: bool = False,
    skip_column_inference: bool = False,
    column_lineage_mode: ColumnLineageMode = ...,
    cli_vars: dict[str, object] | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    resolved_connection: dict[str, object] | None = None,
    analysis_selection: CompileAnalysisSelection | None = None,
) -> CompiledProjectView: ...
def assemble_project(
    *,
    inputs: CompileInputsView,
    inference_profile: ExpressionInferenceProfile | None = None,
    skip_column_inference: bool = False,
    column_lineage_mode: ColumnLineageMode = ...,
    analysis_cache_dir: Path | None = None,
    analysis_model_names: frozenset[str] | None = None,
) -> CompiledProjectView: ...
def build_project_graph_with_analysis_selection(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    analysis_selection: CompileAnalysisSelection,
    selected_target: str | None = None,
    no_sql_validation: bool = False,
    skip_column_inference: bool = False,
    column_lineage_mode: ColumnLineageMode = ...,
    cli_vars: dict[str, object] | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> ProjectGraph: ...
def build_project_graph(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    selected_target: str | None = None,
    no_sql_validation: bool = False,
    skip_column_inference: bool = False,
    column_lineage_mode: ColumnLineageMode = ...,
    cli_vars: dict[str, object] | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    on_progress: Callable[[str], None] | None = None,
    no_cache: bool = False,
) -> ProjectGraph: ...
def discover_project_inputs(
    *,
    project_dir: Path,
    sql_analysis_enabled_override: bool | None = None,
    extract_output_column_locations: bool = True,
) -> DiscoveredProjectInputs: ...
def build_discovered_project_inputs(
    *,
    project_dir: Path,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    sql_analysis_enabled: bool,
    extract_output_column_locations: bool = True,
) -> DiscoveredProjectInputs: ...
def compile_project_phase(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    options: CompilePipelineOptions | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> CompiledProjectPhaseResult: ...
def run_compile_pipeline(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    options: CompilePipelineOptions | None = None,
    hooks: ConnectionHooks | None = None,
) -> CompilePipelineResult: ...
def build_compile_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter_context: CompileAdapterContext,
    selected_target: str | None = None,
    cli_vars: dict[str, object] | None = None,
    run_id: str | None = None,
    no_sql_validation: bool = False,
    defer_model_sql_validation: bool = False,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    resolved_connection: dict[str, object] | None = None,
    no_cache: bool = False,
) -> CompileInputsView: ...
def run_compile_command(
    request: CompileCommandRequest, reuse_attempt: CompileReuseAttempt | None = None
) -> int: ...
def validate_authored_sql_test_ctes(
    test_files: tuple[DiscoveredSqlTestFile, ...],
    scenario_files: tuple[DiscoveredSqlScenarioFile, ...],
    syntax: dict[str, object],
) -> None: ...
def validate_hook_sql_syntax(
    value: object,
    hook_name: str,
    model: tuple[str, Path],
    parsing: tuple[dict[str, str] | None, str | None] = (None, None),
) -> None: ...
def validate_sql_syntax(
    query_sql: str,
    model: tuple[str, Path],
    parsing: tuple[dict[str, str] | None, str | None] = (None, None),
) -> None: ...
def hook_sql_statements(value: object) -> list[str]: ...
def declared_relations(
    inputs: CompileInputsView,
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, dict[str, InferredNullability]],
    dict[str, dict[str, str]],
]: ...
def externally_described_models(
    inputs: DiscoveredProjectInputs, model_schemas: dict[str, ModelSchemaDeclaration]
) -> list[Path]: ...
def resolve_required_columns(
    query_sql: str, references: list[tuple[str, str]], dialect: str | None
) -> list[tuple[str, str, str]]: ...
def public_declaration_indexes(
    inputs: DiscoveredProjectInputs,
) -> tuple[dict[str, EnumDeclaration], dict[str, ConstantDeclaration]]: ...
def public_model_schema_index(
    inputs: DiscoveredProjectInputs,
) -> dict[str, ModelSchemaDeclaration]: ...
def validate_discovered_project_inputs(
    inputs: DiscoveredProjectInputs, nodes: list[dict[str, object]], /
) -> None: ...
def discover_model_files(
    *,
    project_dir: Path,
    extract_implicit_alias_columns: bool,
    extract_output_column_locations: bool,
    selected_model_names: Set[str] | None = None,
    on_fault: Callable[[DiscoveryFileFault], None] | None = None,
) -> tuple[DiscoveredSqlModelFile, ...]: ...
def discover_test_files(
    *,
    project_dir: Path,
    selected_paths: Set[Path] | None = None,
    on_fault: Callable[[DiscoveryFileFault], None] | None = None,
) -> tuple[DiscoveredSqlTestFile, ...]: ...
def discover_scenario_files(
    *, project_dir: Path, on_fault: Callable[[DiscoveryFileFault], None] | None = None
) -> tuple[DiscoveredSqlScenarioFile, ...]: ...
def parse_sql_test_file(
    *, contents: str, file_path: Path
) -> tuple[DiscoveredSqlTestBlock, ...]: ...
def parse_sql_scenario_file(
    *, contents: str, file_path: Path, relative_path: Path
) -> DiscoveredSqlScenarioFile: ...
def discover_source_files(
    *, project_dir: Path, on_fault: Callable[[DiscoveryFileFault], None] | None = None
) -> tuple[DiscoveredSourceFile, ...]: ...
def discover_schema_files(*, project_dir: Path) -> tuple[DiscoveredSchemaFile, ...]: ...
def load_yaml_files(
    request: dict[str, object], relative_paths: list[str], tree: NativeProjectTree
) -> list[tuple[str, object] | Exception]: ...
def load_yaml_document(file_path: str, text: str, kind: str) -> object: ...
def _oracle_read_error(
    errno: int | None, winerror: int | None, message: str, *, file_path: Path
) -> Exception: ...
def discover_enum_files(
    *,
    project_dir: Path,
    on_fault: Callable[[DiscoveryFileFault], None] | None = None,
    isolate_declaration_kind: bool = False,
) -> tuple[DiscoveredEnumFile, ...]: ...
def discover_constant_files(
    *,
    project_dir: Path,
    on_fault: Callable[[DiscoveryFileFault], None] | None = None,
    isolate_declaration_kind: bool = False,
) -> tuple[DiscoveredConstantFile, ...]: ...
def discover_model_schema_files(
    *, project_dir: Path, on_fault: Callable[[DiscoveryFileFault], None] | None = None
) -> tuple[DiscoveredModelSchemaFile, ...]: ...
def discover_sql_function_files(
    *, project_dir: Path, on_fault: Callable[[DiscoveryFileFault], None] | None = None
) -> tuple[DiscoveredSqlFunctionFile, ...]: ...
def discover_sql_hook_files(
    *, project_dir: Path, on_fault: Callable[[DiscoveryFileFault], None] | None = None
) -> tuple[DiscoveredSqlHookFile, ...]: ...
def discover_audit_files(
    *, project_dir: Path, on_fault: Callable[[DiscoveryFileFault], None] | None = None
) -> tuple[DiscoveredAuditFile, ...]: ...
def discover_macro_files(
    *, project_dir: Path, isolate_declaration_kind: bool = False
) -> tuple[DiscoveredMacroFile, ...]: ...
def discover_seed_files(*, project_dir: Path) -> tuple[DiscoveredSeedFile, ...]: ...
def discover_adapter_file(*, project_dir: Path) -> DiscoveredAdapterFile | None: ...
def retained_discovery_session(*, project_dir: Path) -> NativeDiscoverySession | None: ...
def declaration_groups(*, project_dir: Path) -> list[tuple[str, str]]: ...

class NativeDiscoverySession: ...

def parse_declaration_contents(
    request: dict[str, object], names: tuple[str, str], contents: str
) -> str: ...
def parse_model_contents(
    request: dict[str, object], contents: str
) -> tuple[dict[str, object], str, dict[str, SourceLocation]]: ...

class NativeDeclarationContexts:
    def __init__(
        self,
        positions: list[tuple[object, ...]],
        table: tuple[list[int], dict[str, list[int]], dict[str, list[int]]],
        classes: dict[str, object],
        lookups: tuple[dict[str, object], dict[str, object]],
    ) -> None: ...
    def resolve(
        self, resolver: object, file_path: object, resource: object | None = None
    ) -> tuple[Any, bool]: ...

class NativeScopeIndex:
    @property
    def index(self) -> ScopeIndex: ...
    @property
    def has_scoped_relationship_declarations(self) -> bool: ...
    def grant_relationships(
        self,
        *,
        discovered_inputs: DiscoveredProjectInputs,
        syntax: SqlLexicalSyntax,
        scan_store: tuple[SqlTestScanStore | None, str],
    ) -> tuple[tuple[Path, str], ...]: ...
    def index_with_relationships(self) -> ScopeIndex: ...

def open_native_scope_index(
    discovered_inputs: DiscoveredProjectInputs,
    loaded_macros: Mapping[str, LoadedMacro],
    static_macros: tuple[StaticMacroExport, ...],
    /,
) -> NativeScopeIndex: ...
def scope_tolerant_index(
    index: ScopeIndex,
    snapshot: TolerantScopeDiscovery,
    faults: tuple[tuple[StaticMacroFault, ...], tuple[tuple[Path, str], ...]],
    /,
) -> ScopeIndex: ...
def scope_placement_validated_index(
    index: ScopeIndex,
    enforce_placement: bool,
    compile_usages: tuple[UsageRecord, ...] | None,
) -> ScopeIndex: ...
def scope_relocated_declarations(
    index: ScopeIndex, resource: ResourceIdentity, destination: str
) -> tuple[DeclarationRecord, ...] | None: ...

class NativeScopeLookup: ...

def scope_query_target(lookup: ScopeLookup, target: ScopeQueryTarget, /) -> ScopeTargetQuery: ...
@overload
def scope_resolve_visibility(
    lookup: ScopeLookup, target: ScopeQueryTarget, with_reasons: Literal[True], /
) -> VisibilityResolution: ...
@overload
def scope_resolve_visibility(
    lookup: ScopeLookup, target: ScopeQueryTarget, with_reasons: Literal[False], /
) -> DeclarationVisibility: ...
def scope_resolve_path_visibility(
    lookup: ScopeLookup, path: str | PurePath, /
) -> tuple[tuple[DeclarationRecord, ...], tuple[DeclarationRecord, ...]]: ...
def build_scope_lookup(index: ScopeIndex) -> ScopeLookup: ...
def scope_report(
    lookup: ScopeLookup,
    request: tuple[ScopeQueryTarget | None, str | PurePath | None, bool, ScopeReportFilters | None],
    /,
) -> ScopeReport: ...
def scope_explain(
    lookup: ScopeLookup,
    request: tuple[
        str | DeclarationIdentity,
        str | PurePath | ResourceIdentity | None,
        str | PurePath | None,
        bool,
    ],
    /,
) -> tuple[DeclarationExplanation, tuple[ScopeDiagnostic, ...]]: ...
def scope_browse(
    lookup: ScopeLookup,
    request: tuple[str, str | PurePath | ResourceIdentity | None, bool],
    /,
) -> ScopeBrowseResult: ...
def scope_list(
    lookup: ScopeLookup,
    request: tuple[str, ScopeReportFilters | None, str | PurePath | ResourceIdentity | None, bool],
    /,
) -> ScopeListResult: ...
def scope_move_preview(
    lookup: ScopeLookup, resource: str | ResourceIdentity, destination: str | PurePath
) -> tuple[MovePreview | None, tuple[ScopeDiagnostic, ...]]: ...
def serialize_scope_report(report: ScopeReport | ScopeBrowseResult | ScopeListResult) -> str: ...
def scope_metadata_projection(index: ScopeIndex) -> dict[str, JsonValue]: ...
def effective_config_target_name(
    project_config: object, local_config: object, selected: str | None, /
) -> tuple[str | None, str | None]: ...
def effective_config_target_fields(
    configs: tuple[object, object], target_name: str, default_target: object, /
) -> tuple[list[tuple[str | None, str, object]] | None, str | None]: ...
def effective_config_vars(
    configs: tuple[object, object], target_config: object | None, cli_vars: dict[str, object], /
) -> dict[str, object]: ...
def effective_config_connection(
    project_config: object, local_config: object, target_config: object | None, /
) -> tuple[dict[str, object] | None, str | None]: ...
def effective_config_settings(
    settings: tuple[object, object], overrides: frozenset[str], names: list[str], /
) -> dict[str, object]: ...
def yaml_entry_line_index(contents: str, /) -> list[tuple[str, int]]: ...

class NamePattern:
    def __init__(self, pattern: str) -> None: ...
    def matches(self, column_name: str) -> bool: ...

def unresolved_reference_marker_kind(
    sql: str, context: str, /
) -> tuple[int | None, str | None]: ...
def normalize_typed_sql_value(
    raw_value: object, typing: tuple[str, str | None], limits: tuple[int, int, int], /
) -> object: ...
def model_header_declarations(
    header: tuple[object | None, object | None], model_name: str, relative_path: Path, /
) -> tuple[tuple[object, ...], tuple[object, ...]]: ...
def deferred_target_segments(
    template: str, logical: str, context_keys: list[str], variables: list[str], /
) -> list[tuple[bool, str]]: ...
def unknown_mapping_keys(
    keys: list[tuple[str, bool]], allowed: list[str], /
) -> tuple[str, str] | None: ...
def unsupported_keys_help(keys: list[str], supported_keys: list[str], /) -> str: ...
def resource_sql_diagnostic_rows(catalog: object, request: object, /) -> list[object]: ...
def compiler_query_hash(sql: str, dialect: str | None, /) -> str: ...
def function_definition_hash(sql: str, language: str, dialect: str | None, /) -> str: ...
def normalize_query_text(sql: str, /) -> str: ...
def fingerprint_create_table_sql(qualified_name: str, column_types: tuple[str, str], /) -> str: ...
def fingerprint_read_latest_sql(qualified_name: str, /) -> str: ...
def fingerprint_relevant_read_sql(
    read_sql: str,
    node_names: Sequence[str] | None,
    filtered_node_types: Sequence[str],
    /,
) -> str | None: ...
def fingerprint_insert_sql(qualified_name: str, fingerprint: Fingerprint, /) -> str: ...
def fingerprint_insert_batches(
    qualified_name: str,
    fingerprints: Sequence[Fingerprint],
    limits: tuple[int, int],
    /,
) -> list[tuple[tuple[Fingerprint, ...], str]]: ...
def fingerprint_set_from_rows(
    schema: str, qualified_name: str, rows: Sequence[Sequence[object]], /
) -> FingerprintSet: ...
def select_latest_fingerprints(
    fingerprint_set: FingerprintSet,
    node_names: Sequence[str],
    filtered_node_types: Sequence[str],
    /,
) -> FingerprintSet: ...
def glob_name_match(name: str, pattern: str, ignore_case: bool, /) -> bool: ...
def lone_surrogate_site(raw_values: dict[str, object], /) -> tuple[str, str, int] | None: ...
def environment_template_names(values: list[str | None], /) -> list[str]: ...
def contract_model_edit(
    row: tuple[
        str,
        str,
        bool,
        list[tuple[str, str | None, str | None]],
        list[str | None],
        list[tuple[str, str]],
        bool,
    ],
    /,
) -> tuple[str | None, str | None, str | None]: ...
def contract_source_edit(
    row: tuple[str, str, str, list[tuple[str, str | None]], list[tuple[str, str]], bool], /
) -> tuple[str | None, str | None, str | None]: ...
def python_string_locations(
    contents: str, names: list[str], context: str | None
) -> list[tuple[int, int]]: ...
def resource_identity_suggestion(
    name: str, private_identity: bool, /
) -> tuple[str, str] | None: ...
def load_project_config_file(project_dir: Path, /) -> object: ...
def load_local_config_file(project_dir: Path, /) -> object: ...
def resolve_config_file_path(project_dir: Path, local: bool, /) -> Path: ...
def validate_local_sql_analysis(project_dir: Path, flags: tuple[bool, bool, bool], /) -> None: ...
def sql_test_cte_span(
    contents: str, sql_body: str, cte_name: str, call: str | None, /
) -> tuple[int, int, int, int]: ...
def scope_normalize_path(path: str, /) -> tuple[str | None, str | None]: ...
def scope_index_fingerprint(
    project_dir: Path,
    inputs: tuple[list[str], list[str], list[str], list[str], str],
    /,
) -> str | None: ...
def read_scope_index_cache(path: Path, fingerprint: str, /) -> ScopeIndex | None: ...
def write_scope_index_cache(
    location: tuple[Path, str], fingerprint: str, index: ScopeIndex, /
) -> bool: ...
def scope_schema_usages(
    schemas: list[tuple[str, str | None, list[tuple[str, str | None]]]],
    records: list[tuple[tuple[str, str], tuple[str, str, tuple[str, str] | None, str | None, str]]],
) -> tuple[list[tuple[int, int]], list[tuple[list[str], str, str, str]], str | None]: ...

class NativeConfigError:
    class_name: str
    message: str
    code: str | None
    help: str | None
    key: str | None

def column_migration_problem(
    model_name: str, values: dict[str, object], columns: list[tuple[str, str | None]]
) -> NativeConfigError | None: ...
def expand_declaration_references(
    source: tuple[str, list[tuple[int, str, str | None, int, int]], int | None],
    context: object,
    consumer: tuple[object | None, bool, str],
    renderers: tuple[object, dict[str, object]],
) -> tuple[str, list[tuple[int, int, int, int]], list[Any]]: ...
def expand_config_templates(
    value: object,
    sources: tuple[dict[str, object], object, dict[str, str | None]],
    flags: tuple[bool, bool, bool, str],
) -> tuple[object, list[tuple[str, str]]]: ...
def expand_effective_vars(
    raw_values: dict[str, object], environment: object
) -> tuple[object, list[tuple[str, str]]]: ...

class NativeModelConfigBuilder:
    def __init__(
        self,
        layers: tuple[DefaultsConfig, dict[str, dict[str, object]], tuple[type, ...]],
        sources: tuple[dict[str, object], object],
        target: tuple[tuple[str | None, str], tuple[str | None, str | None] | None],
    ) -> None: ...
    def model_config(
        self,
        header: dict[str, object],
        model: tuple[str | None, str],
        classes: dict[str, object],
    ) -> object | NativeConfigError: ...

class NativeModelValidator:
    def __init__(
        self,
        names: tuple[set[str], set[str], set[str], set[str], set[str]],
        custom_materializations: set[str],
        microbatch_concurrency: bool,
    ) -> None: ...
    @staticmethod
    def from_inputs(
        inputs: DiscoveredProjectInputs, microbatch_concurrency: bool
    ) -> NativeModelValidator: ...
    def model_names(self) -> set[str]: ...
    def validate(
        self,
        values: dict[str, object],
        model: tuple[str, str, str],
        facts: tuple[list[tuple[str, str, bool]], Sequence[str] | None, bool, bool],
    ) -> int | NativeConfigError | None: ...
    def references(
        self, model: tuple[str, str], references: list[tuple[str, str, bool]]
    ) -> int | NativeConfigError | None: ...

class SqlCodeScanner:
    def __init__(self, sql: str, syntax: dict[str, object] | None, context: str) -> None: ...
    def non_code_end(self, index: int) -> int | None: ...
    def matching_paren(self, open: int) -> int: ...

class SqlReferenceScanner:
    def __init__(self, syntax: dict[str, object]) -> None: ...
    def extract(
        self, sql: str
    ) -> (
        tuple[
            tuple[
                list[tuple[str, str, str | None, int | None]],
                list[tuple[str, str, int, str, str, str]],
            ],
            None,
        ]
        | tuple[None, tuple[str, int]]
    ): ...

def scope_expected_model_names(
    texts: list[tuple[str, str]], scenario: bool, syntax: dict[str, object]
) -> list[tuple[str | None, list[str]]]: ...
def scope_test_ctes(
    texts: list[tuple[str, str]], syntax: dict[str, object]
) -> list[tuple[str | None, list[tuple[str, str]]]]: ...
def omitted_ceremonial_select(sql: str, syntax: dict[str, object]) -> int | None: ...
def extract_sql_tests_json(request_json: str) -> str: ...
def validated_model_cursor_intrinsics(
    sql: str,
    reserved_markers: list[str],
    model: tuple[str, object, object],
) -> tuple[str | None, str | None]: ...
def replace_cursor_intrinsics(
    sql: str, context: str, replacements: tuple[str, str]
) -> tuple[str, bool, str | None]: ...
def parse_macro_arguments(text: str, nested: list[tuple[int, int]]) -> tuple[object, ...]: ...
def scan_sql_declaration_references(
    sqls: list[str],
) -> list[tuple[list[tuple[int, str, str | None, int, int]], int | None]]: ...
def scan_sql_declaration_usages(
    sqls: list[str],
) -> list[tuple[list[tuple[int, str, str | None, int, int]], int | None]]: ...
def interpolate_sql_batch(
    sqls: list[tuple[str, str]],
    sources: tuple[
        Mapping[str, object],
        Mapping[str, str],
        Mapping[str, str | None] | None,
        Callable[..., str],
    ],
) -> list[
    tuple[str | None, list[tuple[int, int, int, int]], list[tuple[str, str]], str | None]
]: ...
def scan_macro_call_sites(
    sql: str,
) -> tuple[
    list[tuple[int, int, int, str, list[str] | None, bool]],
    tuple[int | None, str | None, str] | None,
]: ...
def extract_sql_relation_names(
    sql: str, dialect: str | None
) -> tuple[list[tuple[str, str | None, str | None]], list[str]] | None: ...
def substitute_placeholder_defaults(sql: str, placeholders: list[tuple[str, str]], /) -> str: ...
def fixture_projection_facts(
    sql: str, dialect: str | None, /
) -> tuple[list[tuple[str, str]], list[str], list[str]]: ...
def macro_call_names(sql: str, nested: bool, /) -> tuple[list[str] | None, str | None]: ...
def inventory_macro_modules(
    sources: list[
        tuple[str, str, list[str], list[str] | None, list[str] | None, str, str, str | None]
    ],
    /,
) -> tuple[
    list[tuple[str, int, list[str], int, str, list[str]]],
    list[tuple[int, str]],
    list[tuple[int, str, list[str]]] | None,
]: ...
def splice_macro_calls(
    sql: str, sites: list[tuple[int, int]], outputs: list[str]
) -> tuple[str, list[tuple[int, int, int, int]]]: ...

class MacroCallMemo:
    def __init__(self) -> None: ...
    def reset_call_classes(self, store_tokens: bool) -> None: ...
    def observe_modules(self, count: int | None) -> None: ...
    def stats(self) -> tuple[int, int, int]: ...
    def attach_store(self, path: str, environment: str) -> tuple[bytes, int]: ...
    def discard_store(self) -> None: ...
    def store_stats(self) -> tuple[int, int]: ...
    def save_store(self, path: str, metadata: bytes) -> int | None: ...

class SqlTestScanStore:
    @staticmethod
    def open_in(
        cache_dir: str, code_identity: str
    ) -> tuple[SqlTestScanStore | None, str | None]: ...
    def counts(self) -> tuple[int, int]: ...
    def save(self) -> tuple[int | None, str | None]: ...

SQL_TEST_SCAN_STORE_FILE_NAME: str

def content_digest(parts: list[str]) -> str: ...
def installed_code_identity(facts: list[str], package_root: str | None) -> str: ...
def compiled_code_identity(installed: str, build_identity: str) -> str: ...
def fingerprint_project_files(root: str, excluded_files: list[str]) -> str: ...
def digest_files(paths: list[str]) -> list[str | None]: ...

# Native analysis: type system.
def normalize_type(
    type_sql: str, dialect: str
) -> tuple[tuple[str, str, str | None, str | None, str | None], str | None]: ...

# Native analysis: model analysis session.
type _AnalysisDiagnosticRow = tuple[str, str, int | None, int | None, int | None, int | None, str]

type _PivotContractRow = tuple[
    str,
    tuple[
        bool,
        list[tuple[str, str | None, str]],
        list[tuple[str, str | None]],
        list[str],
        str | None,
        bool,
    ]
    | None,
]

def locate_model_binding_diagnostics(
    rows: list[_AnalysisDiagnosticRow],
    texts: tuple[str, str, str],
    expansion: tuple[str, list[list[tuple[int, int, int, int]]]] | None,
) -> list[
    tuple[str, str, str, int | None, int | None, tuple[int, int, int | None, int | None] | None]
]: ...

class NativeModelAnalysisSession:
    @property
    def fact_models(self) -> list[str]: ...
    def run(
        self,
    ) -> tuple[list[tuple[str, list[tuple[str, str]]]], list[str]]: ...
    def finish(
        self,
    ) -> tuple[list[tuple[str, list[tuple[str, str]]]], list[str], list[bool]]: ...
    def binding_rows(self) -> list[list[_AnalysisDiagnosticRow]]: ...
    def outcome_rows(self, index: int) -> tuple[Any, Any]: ...
    def prove_dynamic_contracts(
        self, models: list[tuple[str, list[tuple[str, str, str, str, str, str | None]]]], /
    ) -> list[_PivotContractRow]: ...
    @property
    def sharing(self) -> tuple[int, int]: ...
    @property
    def cache_stats(self) -> tuple[int, int, int, str | None] | None: ...

def start_model_analysis_session(
    catalog: object,
    request: tuple[object, ...],
    cache: tuple[str, str] | None = None,
    adapter_rules: tuple[Mapping[str, Callable[..., object]], type] | None = None,
) -> NativeModelAnalysisSession: ...
def prove_dynamic_column_contracts(
    request: tuple[
        str,
        list[tuple[str, list[tuple[str, str]]]],
        list[tuple[str, list[tuple[str, str]]]],
        list[tuple[str, list[tuple[str, str]]]],
        list[tuple[str, list[tuple[str, str, str, str, str, str | None]]]],
        list[tuple[str, list[tuple[str, str, str, str, str, str | None]]]],
    ],
    /,
) -> list[_PivotContractRow]: ...
def infer_query_columns(
    catalog: object | None,
    request: tuple[
        str,
        list[tuple[str, str]],
        list[tuple[str, str]],
        list[tuple[str, list[tuple[str, str]]]],
        list[tuple[str, list[tuple[str, str]]]],
        list[tuple[object, ...]],
        str,
    ],
    adapter_rules: tuple[Mapping[str, Callable[..., object]], type] | None = None,
) -> list[tuple[bool, list[tuple[str, str | None, str]] | None, bool]]: ...
def infer_expression_source_shapes(
    catalog: object,
    request: tuple[str, bool, list[tuple[str, str]], list[tuple[str, str]], list[str]],
    adapter_rules: tuple[Mapping[str, Callable[..., object]], type] | None = None,
) -> list[list[tuple[str, str]] | None]: ...
def _oracle_names_set_operation(sql: str, /) -> bool: ...
def _oracle_cte_fact_recovery(
    request: tuple[
        str,
        str,
        list[tuple[str, list[tuple[str, str]]]],
        list[tuple[str, str]],
        list[tuple[str, str]] | None,
        bool,
        bool,
    ],
    /,
) -> tuple[str | None, list[tuple[str, str]], list[tuple[str, str]], list[str], list[str]]: ...

# Native analysis: semantic completion.
class SemanticTypeRecovery:
    @property
    def status(self) -> str: ...
    @property
    def poisoned(self) -> list[tuple[str, str]]: ...
    @property
    def revalidated(self) -> list[int]: ...
    def finish(
        self, revised: list[list[tuple[str, int | None, int | None]]], /
    ) -> tuple[list[tuple[int, str | None]], list[list[int]]]: ...

def plan_semantic_type_recovery(
    catalog: object,
    request: tuple[
        str | None,
        list[
            tuple[
                str,
                str,
                list[str] | None,
                list[str],
                list[tuple[str, list[tuple[str, str]]]] | None,
                list[tuple[int, str, str, bool]],
                list[tuple[int, str, str, int | None, int | None]],
            ]
        ],
        list[tuple[int, str, bool, str | None]],
    ],
    session: NativeModelAnalysisSession | None = None,
    /,
) -> SemanticTypeRecovery: ...
def check_semantic_metadata_rows(
    catalog: object,
    request: tuple[
        str | None,
        bool,
        list[tuple[str, str]],
        list[tuple[str, list[tuple[str, str]]]],
        list[tuple[str, list[tuple[str, str]]]],
        list[tuple[object, ...]],
        list[str],
        list[tuple[str, str | None, int]],
        list[tuple[int, list[tuple[str, list[str]]]]],
    ],
    /,
) -> tuple[
    list[
        tuple[
            list[tuple[str, str, int, int]],
            list[tuple[str, str, int, int, bool]],
            list[tuple[str, str, int, int]],
        ]
    ],
    list[tuple[int, tuple[str, str, int, int]]],
    list[tuple[int, tuple[str, str, int, int], int]],
    list[str],
]: ...
def complete_semantic_checks(
    catalog: object,
    request: tuple[
        str | None,
        list[
            tuple[
                int,
                str,
                str,
                str | None,
                str | None,
                int | None,
                int | None,
                tuple[int, int, int | None, int | None] | None,
                str | None,
                list[str],
            ]
        ],
        list[
            tuple[
                str,
                str,
                str,
                list[str] | None,
                list[tuple[str, list[tuple[str, str]]]] | None,
                list[str],
                str | None,
            ]
        ],
        list[tuple[str, list[tuple[str, str]]]],
    ],
    session: NativeModelAnalysisSession | None = None,
    /,
) -> tuple[
    list[
        tuple[
            int,
            str,
            str | None,
            list[str],
            tuple[int, int, int | None, int | None] | None,
            int | None,
            int | None,
            bool,
        ]
    ],
    list[list[int]] | None,
    list[tuple[int | None, tuple[int, str, str, str] | None]],
]: ...

# Native analysis: contracts.
type _ContractDiagnosticRow = tuple[
    str, bool, str, str | None, int | None, str | None, tuple[str, str] | None, str
]

def evaluate_project_model_contracts(
    settings: tuple[str, bool], project: NativeCompiledProject
) -> list[
    tuple[
        str,
        list[
            tuple[str, bool, str, str | None, int | None, str | None, tuple[str, str] | None, str]
        ],
    ]
]: ...
def project_promotion_conflicts(
    settings: tuple[str | None, str, str], project: NativeCompiledProject
) -> list[tuple[str, str, str, str, str]]: ...
def build_project_column_lineage(
    project: CompiledProjectView,
    dialect: str | None,
    mode: ColumnLineageMode,
    model_names: frozenset[str] | None,
    /,
) -> ProjectColumnLineage | None: ...
def build_direct_semantic_uses(
    project: CompiledProjectView,
    dialect: str | None,
    model_names: frozenset[str],
    /,
) -> tuple[DirectSemanticColumnUse, ...]: ...
def render_dependency_tree[Node: Hashable](
    *,
    focus: Node,
    deps: dict[Node, list[Node]],
    seen: set[Node],
    format_node: Callable[[Node], str],
    sort_key: Callable[[Node], SupportsRichComparison],
    branch_style: Callable[[str], str],
    already_shown: Callable[[], str],
) -> list[str]: ...
def render_column_trace_tree[Column, Edge](
    *,
    target: Column,
    deps: dict[str, list[Edge]],
    total: int,
    limit: int,
    column_id: Callable[[Column], str],
    related_column: Callable[[Edge], Column],
    format_related: Callable[[Edge], str],
    branch_style: Callable[[str], str],
    already_shown: Callable[[], str],
    note_style: Callable[[str], str],
) -> list[str]: ...
def render_column_trace_limit_note(
    *, total: int, limit: int, note_style: Callable[[str], str]
) -> list[str]: ...
def serialize_column(
    *,
    column: QualifiedLineageColumn,
    render_resource_type: Callable[[QualifiedLineageColumn], str],
) -> dict[str, object]: ...
def serialize_column_edge(
    *,
    edge: ColumnLineageEdge,
    render_resource_type: Callable[[QualifiedLineageColumn], str],
) -> dict[str, object]: ...

class ProjectColumnLineage:
    """Project-level column lineage graph with lazily materialized public views."""

    def __init__(
        self,
        *,
        models: dict[str, ModelColumnLineage],
        edges: tuple[ColumnLineageEdge, ...],
    ) -> None: ...
    @classmethod
    def from_fast_facts(
        cls,
        *,
        models: dict[str, ModelColumnLineage],
        compact_models: dict[str, tuple[Sequence[CompiledLineageColumnFact], bool]],
        model_order: tuple[str, ...],
    ) -> ProjectColumnLineage: ...
    @property
    def models(self) -> dict[str, ModelColumnLineage]: ...
    @property
    def edges(self) -> tuple[ColumnLineageEdge, ...]: ...
    def has_model(self, model_name: str, /) -> bool: ...
    def model_has_star(self, model_name: str, /) -> bool: ...
    def edge_count_targeting(self, model_name: str, /) -> int: ...
    def edges_targeting(self, model_name: str, /) -> tuple[ColumnLineageEdge, ...]: ...
    def edges_sourced_from(self, resource_name: str, /) -> tuple[ColumnLineageEdge, ...]: ...
    def column_consumers(
        self, *, resource_name: str, column_name: str
    ) -> tuple[ColumnLineageEdge, ...]: ...

def relation_lineage_fingerprint(
    project_dir: Path, prefix: bytes, interrupted_listing_uncacheable: bool, /
) -> str | None: ...

# Native analysis: SQL test planning glue.
def plan_compiled_sql_tests(
    request: NativeSqlTestPlanningRequest, /
) -> tuple[list[NativeSqlTestPlanRow], int, int]: ...
def resolve_compiled_sql_test_chains(request: NativeSqlTestChainRequest, /) -> list[list[str]]: ...
def assemble_compiled_sql_tests(
    request: NativeSqlTestAssemblyRequest, /
) -> list[NativeSqlTestAssemblyRow]: ...

# Native analysis: compiled project assembly.
def sql_syntax_error(
    sql: str,
    placeholders: Mapping[str, str] | None,
    dialect: str | None,
    parse_one: bool = False,
) -> str | None: ...
def check_native_sql_syntax(
    request: tuple[str, list[tuple[str, list[tuple[str, str]]]]], /
) -> bool: ...
def assemble_project_resource_facts(
    request: tuple[
        str,
        tuple[str | None, str | None, str | None] | None,
        tuple[str | None, str | None, str | None, str | None],
        list[tuple[str, str, str, tuple[str, str] | None]],
        list[tuple[str, str | None]],
        list[
            tuple[
                str,
                str,
                list[str],
                list[tuple[str, str, str | None]],
                list[tuple[str, list[tuple[str, str]]]],
            ]
        ],
        list[tuple[str, bool, str | None, str | None]],
        list[tuple[str, list[str], str | None, str | None]],
        list[tuple[str, str, list[str], list[tuple[str, str, str | None]]]],
        list[tuple[list[tuple[str, str, str | None]], tuple[str, str] | None]],
    ],
    /,
) -> tuple[
    list[list[tuple[str, str]]],
    list[tuple[str | None, str | None] | None],
    list[tuple[str | None, str | None, str | None, str | None]],
    list[list[tuple[str, str]]],
    list[list[tuple[str, str]]],
    list[tuple[str, str]],
    list[bool],
    tuple[str, int, str, str, str | None, int | None] | None,
]: ...
def check_native_explicit_references(request_json: str, /) -> str: ...
def native_execution_gate_edges(
    request_json: str, /
) -> tuple[
    list[tuple[str, tuple[str, str], tuple[str, str], tuple[str, str]]],
    list[tuple[str, tuple[str, str], tuple[str, str], str, str | None]],
]: ...
def schema_validation_rows(
    catalog: Any,
    dialect: str,
    requests: list[tuple[str, list[tuple[str, bool]], dict[str, Mapping[str, str]]]],
) -> list[list[tuple[str, str, int | None, int | None, int | None, int | None, str]]]: ...
def python_literal_sql_calls(
    source: str, start_line: int, placeholder: str
) -> list[tuple[str, str, int]]: ...
def _oracle_json_dumps(dialect_json: str, value_json: str) -> str: ...
def _oracle_text_positions(
    data: bytes, byte_offsets: list[int]
) -> tuple[str, list[tuple[int, int, int] | None]]: ...
def _oracle_yaml_load(text: str) -> str: ...
def _oracle_toml_load(text: str) -> str: ...
