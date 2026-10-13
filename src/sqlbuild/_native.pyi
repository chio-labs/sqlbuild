"""Private SQLBuild native engine bindings."""

from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence, Set
from contextlib import AbstractContextManager
from pathlib import Path, PurePath
from typing import Any, Literal, TypedDict, overload

from _typeshed import SupportsRichComparison

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.strict_adapter import StrictAdapter
from sqlbuild.adapter.contract.models import ColumnInfo, ExpressionInferenceProfile, RelationInfo
from sqlbuild.adapter.contract.types import (
    AdapterExecute,
    FrameworkType,
    TablePromotionMode,
    TypeDialect,
)
from sqlbuild.cli.commands.types import CompileLineageMode
from sqlbuild.cli.compile.models import CompileAnalysis
from sqlbuild.cli.compile_reuse.models import CompileReuseAttempt
from sqlbuild.cli.entry.models import CompileCommandRequest, CompileProfileFlags
from sqlbuild.cli.output.models import WrittenTarget
from sqlbuild.compiler.auditing.models import (
    AuditGateIdentity,
    MeasurementContract,
    MeasurementThresholds,
)
from sqlbuild.compiler.auditing.types import AuditEvaluationMode, AuditOutcome, AuditSeverity
from sqlbuild.compiler.compile.classes.sql_test_scan_cache import SqlTestScanCache
from sqlbuild.compiler.compile.models import (
    CompileAdapterContext,
    CompileAnalysisSelection,
    CompileAuditInput,
    CompiledAudit,
    CompiledFunction,
    CompiledLineageColumnFact,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
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
    CursorInputRoles,
    DeclarationResolutionContext,
    DeclarationScopeBuild,
    DeclarationScopeResolver,
    DynamicColumnContractProof,
    FunctionArgument,
    FunctionReturnColumn,
    InferredColumn,
    LoadedMacro,
    MacroContext,
    ModelInputBuildContext,
    NativeModelConfigInputs,
    NativeModelConfigSession,
    PythonSqlReferenceReport,
    SqlReferenceScan,
    StaticMacroExport,
)
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
    AuditInput,
    CompiledAuditView,
    CompiledFunctionView,
    CompiledModelView,
    CompiledProjectView,
    CompiledSeedView,
    CompiledSourceView,
    CompileInputsView,
    FunctionInput,
    FunctionLanguage,
    ModelInput,
    SeedInput,
    SourceInput,
    TypedSqlValueRenderer,
)
from sqlbuild.compiler.contract_adoption.models import ContractEvidence, ContractFinding
from sqlbuild.compiler.contracts.models import ContractValidationResult
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
from sqlbuild.compiler.fingerprints.types import FingerprintWriteProgress
from sqlbuild.compiler.frontier.types import CompilerStage
from sqlbuild.compiler.graph.models import AttachedAuditGateEdge, HookReadEdge, LineageGraphViews
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
    PythonPlanEntry,
    PythonRunPlanOutputs,
    StaticCommandContext,
)
from sqlbuild.compiler.planner.models import (
    AuditPlanEntry,
    DeferralInputs,
    FutureCursorSafetyEvidence,
    MaximumStartSafetyEvidence,
    PlanOutput,
)
from sqlbuild.compiler.python_nodes.models import (
    PythonNodeGraph,
    PythonNodeIdentity,
    PythonSqlRunLifecyclePlan,
    PythonSqlRunSelection,
)
from sqlbuild.compiler.refactoring.models import ManualLocation
from sqlbuild.compiler.references.models import (
    LiteralSqlRelation,
    ProjectRelation,
    ProjectRelationIndex,
    RelationName,
)
from sqlbuild.compiler.references.types import (
    ExternalSqlReferenceResolver,
    HardCodedRelationOwnerKind,
)
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
from sqlbuild.compiler.sql_analysis.models import (
    SqlBindingResult,
    SqlLexicalSyntax,
    SqlSchemaValidationRequest,
)
from sqlbuild.compiler.sql_analysis.types import NativeProjectCatalog
from sqlbuild.compiler.sql_test_glue.models import (
    NativeSqlTestAssembly,
    NativeSqlTestChainRequest,
    NativeSqlTestPlanningRequest,
)
from sqlbuild.compiler.sql_test_glue.types import NativeSqlTestPlanRow
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.models import BuildExecutionResult, SeedExecutionResult
from sqlbuild.executor.clone.models import CloneExecutionResult
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes.models import (
    PythonCheckExecutionResult,
    PythonNodeExecutionResult,
)
from sqlbuild.executor.scenario.models import ScenarioRunResult, ScenarioSnapshotCaptureRunResult
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.lint.types import RelationKeyRow
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.presentation.models import DisplayOptions
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.runtime.contracts.models import ConnectionHooks
from sqlbuild.runtime.observability.models import LifecycleEvent
from sqlbuild.spec.contracts.models import (
    DefaultsConfig,
    LocalConfig,
    ProjectConfig,
    ScenarioConfig,
    SchemaColumn,
    SchemaAuditInstance,
    SchemaDynamicColumnFamily,
    SchemaModelEntry,
    SchemaSeedEntry,
    SettingsConfig,
    SourceEntry,
    SourceLocation,
    TargetConfig,
)
from sqlbuild.sql_values.models import SqlValue

BUILD_IDENTITY: str
STAGE_CAPTURE_OMITTED_ATTRIBUTES: dict[str, frozenset[str]]

class CompileInputReads:
    """Environment, settings, and run-identity reads observed during one compile."""

    def __init__(self) -> None: ...
    def add_environment_name(self, name: str) -> None: ...
    def add_settings_class(self, settings_class: type) -> None: ...
    def mark_run_id_read(self) -> None: ...
    @property
    def environment_names(self) -> tuple[str, ...]: ...
    @property
    def settings_classes(self) -> tuple[type, ...]: ...
    @property
    def read_run_id(self) -> bool: ...

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

def compiled_model_record(model: CompiledModelView) -> CompiledModel: ...
def compiled_audit_record(audit: CompiledAuditView) -> CompiledAudit: ...
def compiled_function_record(function: CompiledFunctionView) -> CompiledFunction: ...
def compiled_source_record(source: CompiledSourceView) -> CompiledSource: ...
def compiled_seed_record(seed: CompiledSeedView) -> CompiledSeed: ...
def compiled_project_record(
    project: CompiledProjectView, *, include_sql_expansions: bool = True
) -> CompiledProject: ...
def with_binding_diagnostics(
    *, model: CompiledModelView, diagnostics: tuple[CompilerDiagnostic, ...]
) -> CompiledModelView: ...
def with_type_recovery(
    *,
    model: CompiledModelView,
    diagnostics: tuple[CompilerDiagnostic, ...],
    poisoned: frozenset[tuple[str, str]],
) -> CompiledModelView: ...
def project_with(*, project: CompiledProjectView, **changes: Any) -> CompiledProjectView: ...
def inputs_with(*, inputs: CompileInputsView, **changes: Any) -> CompileInputsView: ...
def compile_inputs_view(
    *, fields: dict[str, Any], native_project: NativeCompiledProject | None
) -> CompileInputsView: ...
def plain_typed_value(value: SqlValue) -> object: ...
def declaration_rows(
    *, enums: Sequence[EnumDeclaration], constants: Sequence[ConstantDeclaration]
) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]: ...
def record_model_analyses(
    *, project: NativeCompiledProject, models: Sequence[CompiledModelView]
) -> int: ...
def compiled_project_facts(project: CompiledProjectView) -> NativeCompiledProject: ...
def attach_resources(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    native_project: NativeCompiledProject,
    settings: tuple[SettingsConfig, TargetConfig | None, str],
    no_sql_validation: bool,
    python_functions_inherit_default_namespace: bool,
) -> tuple[tuple[SeedInput, ...], tuple[FunctionInput, ...], tuple[SourceInput, ...]]: ...
def attach_checks(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    native_project: NativeCompiledProject,
    settings: tuple[SettingsConfig, TypedSqlValueRenderer, SqlLexicalSyntax],
    scan_cache: SqlTestScanCache,
    source_inputs: tuple[SourceInput, ...],
) -> tuple[
    tuple[CompileSqlTestInput, ...],
    tuple[CompileSqlScenarioInput, ...],
    tuple[AuditInput, ...],
    tuple[CompilerDiagnostic, ...],
]: ...
def build_effective_connection(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    target_config: TargetConfig | None,
    effective_vars: dict[str, object],
) -> dict[str, object]: ...
def build_effective_settings(
    *, project_config: ProjectConfig, local_config: LocalConfig
) -> SettingsConfig: ...
def build_effective_vars(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    target_config: TargetConfig | None,
    cli_vars: dict[str, object],
) -> dict[str, object]: ...
def native_model_config_session(
    *, inputs: NativeModelConfigInputs, validator: NativeModelValidator
) -> NativeModelConfigSession: ...
def build_model_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    context: ModelInputBuildContext,
    no_sql_validation: bool = False,
    defer_model_sql_validation: bool = False,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    native_project: NativeCompiledProject,
) -> tuple[ModelInput, ...]: ...
def build_compile_target_context(
    *, discovered_inputs: DiscoveredProjectInputs, selected_target: str | None, no_cache: bool
) -> tuple[str | None, TargetConfig | None, Path | None]: ...
def build_effective_target_namespace(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    selected_target: str | None,
    connection_database: object | None,
    connection_schema: object | None,
    default_database: str | None,
    default_schema: str | None,
) -> tuple[str | None, TargetConfig | None, str | None, str | None]: ...
def build_declaration_scope(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    loaded_macros: dict[str, LoadedMacro],
    sql_lexical_syntax: SqlLexicalSyntax,
    compile_cache_dir: Path | None = None,
) -> DeclarationScopeBuild: ...
def rebind_declaration_scope(
    *,
    scope: DeclarationScopeBuild,
    discovered_inputs: DiscoveredProjectInputs,
    loaded_macros: dict[str, LoadedMacro],
) -> DeclarationScopeBuild | None: ...

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

class CompileArtifactWrites:
    @property
    def artifacts(self) -> dict[str, tuple[str | None, int | None, int | None]]: ...

class RecordedCompileOutput:
    def print_stderr_line(self, line: str) -> None: ...
    def record_stdout(self, text: str) -> None: ...
    def print_stdout(self) -> None: ...
    @property
    def stderr_lines(self) -> list[str]: ...
    @property
    def stdout(self) -> str | None: ...

def format_plan(
    *,
    plan: PlanOutput,
    full_refresh: bool = False,
    use_color: bool = True,
    include_header: bool = True,
    display_options: DisplayOptions | None = None,
    python_plan_entries: tuple[PythonPlanEntry, ...] = (),
    include_direct_freshness_diagnostics: bool = True,
    include_completion: bool = False,
) -> str: ...

class TerminalEventClaim:
    @property
    def terminal(self) -> LifecycleEvent: ...
    @property
    def event_sequence(self) -> int: ...

class TerminalEventIndex:
    def __init__(self) -> None: ...
    def consume(self, event: LifecycleEvent) -> None: ...
    def claim_resource_terminal(
        self,
        *,
        resource_name: str,
        resource_id: str | None = None,
        resource_attempt_id: str | None = None,
        attempt_number: int | None = None,
    ) -> TerminalEventClaim | None: ...
    def resource_terminal(
        self, *, resource_name: str, resource_id: str | None = None
    ) -> LifecycleEvent | None: ...
    def lifecycle_terminal(self) -> LifecycleEvent | None: ...
    def output_serialization_scope(self) -> AbstractContextManager[bool]: ...
    def events(self) -> tuple[LifecycleEvent, ...]: ...

class TerminalEventIndexScope:
    def __enter__(self) -> TerminalEventIndex: ...
    def __exit__(self, *exc_info: object) -> bool: ...

def current_terminal_event_index() -> TerminalEventIndex | None: ...
def terminal_event_index_scope(index: TerminalEventIndex) -> TerminalEventIndexScope: ...
def format_build_execution_json(
    *,
    result: BuildExecutionResult,
    plan: PlanOutput,
    python_node_results: tuple[PythonNodeExecutionResult, ...] = (),
    python_check_results: tuple[PythonCheckExecutionResult, ...] = (),
    command: str = "build",
    run_id: str | None = None,
    cost: dict[str, object] | None = None,
) -> str: ...
def format_seed_execution_json(
    *, results: tuple[SeedExecutionResult, ...], plan: PlanOutput
) -> str: ...
def format_load_execution_json(*, results: tuple[LoadExecutionResult, ...]) -> str: ...
def format_clone_execution_json(
    *, result: CloneExecutionResult, resource_types_by_name: Mapping[str, str]
) -> str: ...
def format_test_execution_json(*, results: tuple[SqlTestExecutionResult, ...]) -> str: ...
def format_audit_execution_json(
    *,
    results: tuple[AuditExecutionResult, ...],
    configured_concurrency: int = 1,
    worker_count: int | None = None,
) -> str: ...
def format_scenario_execution_json(
    *,
    results: tuple[ScenarioRunResult, ...],
    local: bool = False,
    run_namespace: str | None = None,
    namespace_source: str = "unset",
    duration_ms: float | None = None,
) -> str: ...
def format_scenario_snapshot_execution_json(
    *,
    results: tuple[ScenarioSnapshotCaptureRunResult, ...],
    refresh: bool = False,
    run_namespace: str | None = None,
    namespace_source: str = "unset",
) -> str: ...
def format_degradable_build_execution_json(
    *,
    result: BuildExecutionResult,
    plan: PlanOutput,
    execution_succeeded: bool,
    python_node_results: tuple[PythonNodeExecutionResult, ...] = (),
    python_check_results: tuple[PythonCheckExecutionResult, ...] = (),
    command: str = "build",
    run_id: str | None = None,
    cost: dict[str, object] | None = None,
) -> str: ...
def write_execution_json_output(
    *, payload: str, json_output: bool, json_output_path: Path | None
) -> None: ...
def format_plan_json(
    *, plan: PlanOutput, python_plan_entries: tuple[PythonPlanEntry, ...] = ()
) -> str: ...
def serialize_future_cursor_safety(
    evidence: FutureCursorSafetyEvidence | None,
) -> dict[str, object] | None: ...
def serialize_maximum_start_safety(
    evidence: MaximumStartSafetyEvidence | None,
) -> dict[str, object] | None: ...
def write_reusable_compile(
    *,
    attempt: CompileReuseAttempt,
    output: RecordedCompileOutput,
    exit_code: int,
    input_reads: CompileInputReads,
    artifact_writes: CompileArtifactWrites,
    compile_cache_enabled: bool,
    artifacts_written: bool,
    dag_artifact_path: Path | None,
    json_output: bool,
) -> None: ...
def format_compile_text(
    *,
    graph: ProjectGraph,
    written: WrittenTarget,
    manifest: bool,
    lineage: ProjectColumnLineage | None,
    diagnostics: tuple[CompilerDiagnostic, ...],
    lineage_mode: CompileLineageMode = ...,
    use_color: bool,
    selected_keys: frozenset[CompiledObjectKey] | None = None,
    sql_validation_enabled: bool = True,
) -> str: ...
def format_compile_json(
    *,
    graph: ProjectGraph,
    written: WrittenTarget,
    manifest: bool,
    timings_ms: dict[str, int],
    lineage: ProjectColumnLineage | None,
    diagnostics: tuple[CompilerDiagnostic, ...],
    lineage_mode: CompileLineageMode = ...,
    selected_keys: frozenset[CompiledObjectKey] | None = None,
    sql_validation_enabled: bool = True,
) -> str: ...
def format_compile_error_json(
    *, code: str, message: str, help_text: str | None, location: SourceLocation | None = None
) -> str: ...

class PlannedStaticSqlTests: ...

def write_static_compile_target(
    *,
    target_dir: Path,
    adapter: BaseAdapter,
    project: CompiledProjectView,
    manifest: NativeManifest | None = None,
) -> WrittenTarget: ...
def write_compile_target(
    *,
    target_dir: Path,
    adapter: BaseAdapter,
    plan_output: PlanOutput,
    manifest: NativeManifest | None = None,
) -> WrittenTarget: ...
def static_sql_test_planning_diagnostics(
    *, target_dir: Path, adapter: BaseAdapter, project: CompiledProjectView
) -> tuple[CompilerDiagnostic, ...]: ...
def plan_static_sql_tests(
    *, target_dir: Path, adapter: BaseAdapter, project: CompiledProjectView
) -> PlannedStaticSqlTests: ...

class PreparedCompileArtifacts:
    min_prepared_models: int
    max_prepared_models: int
    def __init__(self, *, enabled: bool) -> None: ...
    @property
    def enabled(self) -> bool: ...
    def __enter__(self) -> PreparedCompileArtifacts: ...
    def __exit__(self, *exception: object) -> None: ...
    def remove_abandoned_staging(self, *, target_dir: Path) -> None: ...
    def create_staging_directory(self, staging_dir: Path) -> None: ...
    def start(
        self,
        *,
        project: CompiledProjectView,
        adapter: BaseAdapter,
        target_dir: Path,
        stage_artifacts: bool,
    ) -> None: ...
    def publish(
        self, *, target_dir: Path, manifest: NativeManifest | None
    ) -> WrittenTarget | None: ...
    def planning_diagnostics(self) -> tuple[CompilerDiagnostic, ...] | None: ...

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

class NativeDirectorySnapshot:
    @property
    def project_dir(self) -> Path: ...
    @property
    def memo(self) -> dict[object, object]: ...

class NativeDirectorySnapshotScope:
    def __enter__(self) -> NativeDirectorySnapshot: ...
    def __exit__(self, *exc_info: object) -> bool: ...

def directory_snapshot_scope(*, project_dir: Path) -> NativeDirectorySnapshotScope: ...
def active_directory_snapshot(*, project_dir: Path) -> NativeDirectorySnapshot | None: ...

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
def compile_frontier[T](
    *,
    until: CompilerStage,
    python_stage: Callable[[], T],
    native_stage: Callable[[], T] | None = None,
) -> T: ...
def render_stage_capture(value: object) -> str: ...
def digest_module_files(paths: Iterable[str], /) -> dict[str, str] | None: ...
def module_digests_metadata(digests: dict[str, str], /) -> bytes: ...
def unchanged_module_digests(
    *, metadata: bytes, known: dict[str, str]
) -> dict[str, str] | None: ...
def macro_store_token(
    *, loaded: LoadedMacro, identity: DeclarationIdentity | None
) -> str | None: ...
def context_store_token(
    *, macro_context: MacroContext, declarations: DeclarationResolutionContext | None
) -> str | None: ...
def mask_capture_noise(text: str) -> str: ...
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
def validate_named_target_schema_strategy(
    *, discovered_inputs: DiscoveredProjectInputs, adapter: BaseAdapter, selected_target: str | None
) -> None: ...
def validate_managed_loader_target_isolation(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    resolved_connection: dict[str, object] | None = None,
) -> None: ...
def validate_project_targets(*, adapter_name: str, project: CompiledProjectView) -> None: ...
def validate_managed_write_schemas(
    *, adapter: BaseAdapter, project: CompiledProjectView
) -> None: ...
def resolve_cursor_input_roles(*, model: CompiledModelView) -> CursorInputRoles: ...
def model_placeholders(model_input: ModelInput, /) -> dict[str, str] | None: ...
def model_syntax_checks(
    *,
    model_inputs: tuple[ModelInput, ...],
    analysis_model_names: frozenset[str] | None,
    analysis_succeeded: frozenset[str],
) -> tuple[tuple[tuple[str, dict[str, str] | None], ...], ...]: ...
def standalone_pivot_models(
    *, model_inputs: tuple[ModelInput, ...], analysed: Mapping[str, int]
) -> dict[int, tuple[str, tuple[SchemaDynamicColumnFamily, ...]]]: ...
def resolve_compile_analysis_selection(
    *, options: CompilePipelineOptions, discovered_inputs: DiscoveredProjectInputs
) -> CompileAnalysisSelection | None: ...
def build_project_graph_from_compiled_project(*, project: CompiledProjectView) -> ProjectGraph: ...
def plan_has_executable_work(
    *, plan: PlanOutput, python_plan_entries: tuple[PythonPlanEntry, ...] = ()
) -> bool: ...
def build_static_pipeline_result(
    *, context: StaticCommandContext, plan_output: PlanOutput
) -> CompilePipelineResult: ...
def run_compile_only_pipeline(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    options: CompilePipelineOptions,
    on_progress: Callable[[str], None] | None = None,
) -> CompilePipelineResult: ...
def build_deferred_locations(
    *,
    project: CompiledProjectView,
    deferred_target_config: TargetConfig,
    effective_vars: dict[str, object],
    default_schema: str | None,
    default_database: str | None,
    render_qualified_name: Callable[..., str | None],
) -> dict[str, CompiledRelationLocation]: ...
def resolve_deferred_target_config(
    *, discovered_inputs: DiscoveredProjectInputs, defer_to: str, current_target_name: str | None
) -> TargetConfig: ...
def gather_deferred_relations(
    *,
    adapter: BaseAdapter,
    connection: Any,
    deferred_locations: dict[str, CompiledRelationLocation],
) -> dict[str, RelationInfo]: ...
def resolve_model_deferral_inputs(
    *,
    project: CompiledProjectView,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection: Any,
    defer_to: str | None,
) -> DeferralInputs: ...
def build_python_relation_targets(
    *,
    adapter: BaseAdapter,
    project: CompiledProjectView,
    plan_output: PlanOutput,
    required_refs: frozenset[SqlResourceRef] | None = None,
) -> dict[SqlResourceRef, str]: ...
def build_project_relation_targets(
    *, adapter: BaseAdapter, plan_output: PlanOutput
) -> dict[SqlResourceRef, str] | None: ...
def resolve_diff_model_names(
    *, project: CompiledProjectView, select: tuple[str, ...], exclude: tuple[str, ...]
) -> tuple[str, ...]: ...
def run_diff_pipeline(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    from_target: str,
    to_target: str,
    resolved_connection: dict[str, object],
    no_sql_validation: bool,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    cli_vars: dict[str, object] | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
) -> tuple[CompiledProjectView, CompiledProjectView, tuple[str, ...]]: ...
def python_read_source_names_for(
    *, discovered_inputs: DiscoveredProjectInputs, python_node_names: frozenset[str]
) -> frozenset[str]: ...
def build_python_run_plan_outputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    plan_output: PlanOutput,
    run_selection: PythonSqlRunSelection | None,
    selected_python_node_names: frozenset[str],
) -> PythonRunPlanOutputs: ...
def build_python_plan_entries(
    *,
    lifecycle_plan: PythonSqlRunLifecyclePlan,
    python_graph: PythonNodeGraph,
    previous_identities: dict[tuple[str, str], Fingerprint] | None = None,
) -> tuple[PythonPlanEntry, ...]: ...
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
def discover_scope_snapshot(*, project_dir: Path) -> TolerantScopeDiscovery: ...
def discover_python_module_files(
    *, project_dir: Path, root: str, public_only: bool
) -> tuple[Path, ...]: ...
def discover_python_hook_files(*, project_dir: Path) -> tuple[dict[str, Any], ...]: ...
def discover_python_function_files(
    *, project_dir: Path
) -> tuple[DiscoveredPythonFunctionFile, ...]: ...

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

def assert_no_unresolved_sql_markers(*, sql: str, context: str) -> None: ...
def normalize_typed_sql_value(
    raw_value: object, typing: tuple[str, str | None], limits: tuple[int, int, int], /
) -> object: ...
def model_header_declarations(
    header: tuple[object | None, object | None], model_name: str, relative_path: Path, /
) -> tuple[tuple[object, ...], tuple[object, ...]]: ...
def unknown_mapping_keys(
    keys: list[tuple[str, bool]], allowed: list[str], /
) -> tuple[str, str] | None: ...
def unsupported_keys_help(keys: list[str], supported_keys: list[str], /) -> str: ...
def semantic_help_catalogue() -> list[tuple[str, str]]: ...
def resource_sql_diagnostics_of(
    catalog: object,
    project: Any,
    shapes: dict[str, dict[str, str]],
    profile: ExpressionInferenceProfile,
    /,
) -> tuple[CompilerDiagnostic, ...]: ...
def compute_query_hash(*, query_sql: str, dialect: str | None) -> str: ...
def compute_function_definition_hash(
    *, fingerprint_sql: str, language: str, dialect: str | None
) -> str: ...
def normalize_query_sql(query_sql: str, /) -> str: ...
def build_create_table_sql(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
) -> str: ...
def build_read_latest_sql(
    *, database: str | None, schema: str, render_qualified_name: Callable[..., str | None]
) -> str: ...
def read_latest_fingerprints(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    table_exists: bool,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_read_latest_sql: Callable[..., str],
    require_table: bool = False,
    node_names: tuple[str, ...] | None = None,
    filtered_node_types: tuple[str, ...] = (),
) -> FingerprintSet: ...
def write_fingerprint(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    database: str | None,
    schema: str,
    fingerprint: Fingerprint,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    render_create_table_sql: Callable[..., str] | None = None,
    render_create_index_sqls: Callable[..., tuple[str, ...]] | None = None,
) -> None: ...
def write_fingerprints(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    database: str | None,
    schema: str,
    fingerprints: Sequence[Fingerprint],
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    render_create_table_sql: Callable[..., str] | None = None,
    render_create_index_sqls: Callable[..., tuple[str, ...]] | None = None,
    on_progress: FingerprintWriteProgress | None = None,
) -> None: ...
def select_latest_fingerprints(
    *,
    fingerprint_set: FingerprintSet,
    node_names: tuple[str, ...],
    filtered_node_types: tuple[str, ...] = (),
) -> FingerprintSet: ...
def lone_surrogate_site(raw_values: dict[str, object], /) -> tuple[str, str, int] | None: ...
def environment_template_names(values: list[str | None], /) -> list[str]: ...
def find_python_string_locations(
    *,
    project_dir: Path,
    discovered: DiscoveredProjectInputs,
    names: tuple[str, ...],
    reason: str,
    context: str | None = None,
) -> tuple[ManualLocation, ...]: ...
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
def scope_index_fingerprint(*, project_dir: Path) -> str | None: ...
def load_or_build_scope_index(*, project_dir: Path, no_cache: bool = False) -> ScopeIndex: ...
def model_schema_scope_usages(
    schema_files: Sequence[DiscoveredModelSchemaFile],
    resolver: DeclarationScopeResolver | None,
    /,
) -> tuple[UsageRecord, ...]: ...

class NativeConfigError:
    class_name: str
    message: str
    code: str | None
    help: str | None
    key: str | None

def parse_schema_columns(
    raw_columns: object,
    site: tuple[str, str],
    options: tuple[bool, bool, bool],
    column_locations: dict[str, SourceLocation],
) -> tuple[SchemaColumn, ...]: ...
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

def scan_sql_reference_calls(*, sql: str, syntax: SqlLexicalSyntax) -> SqlReferenceScan: ...
def extract_sql_references(
    *, sql: str, syntax: SqlLexicalSyntax
) -> tuple[CompileSqlReference, ...]: ...

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
def parse_cli_arguments(
    argv: list[str], defaults: list[tuple[str, object]], *, use_color: bool, columns: int
) -> tuple[list[tuple[str, object]] | None, int | None]: ...
def run_cli(argv: Sequence[str] | None = None, handlers: object | None = None) -> int: ...
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
def extract_relation_names(
    *, sql: str, dialect: str | None
) -> tuple[tuple[RelationName, ...], frozenset[str]] | None: ...
def match_project_relation(
    *,
    index: ProjectRelationIndex,
    relation: RelationName,
    default_database: str | None = None,
    default_schema: str | None = None,
) -> ProjectRelation | None: ...
def runtime_project_relations(
    *, relations: Mapping[SqlResourceRef, str], dialect: str | None
) -> ProjectRelationIndex: ...
def render_source_relation(*, entry: SourceEntry, adapter: StrictAdapter | None = None) -> str: ...
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
def analyze_native_model_sql(*, request: Any) -> Any: ...
def session_outcome_analysis(
    *, session: Any, position: int, placeholders: dict[str, str] | None
) -> Any: ...
def dynamic_contract_proof(row: Any, /) -> Any: ...
def infer_native_query_column_rows(
    *,
    queries: Sequence[Any],
    profile: Any,
    column_nullability_by_table: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[tuple[bool, list[tuple[str, str | None, str]] | None, bool]]: ...
def infer_native_query_columns(
    *,
    queries: Sequence[Any],
    profile: Any,
    column_types_by_table: Mapping[str, Mapping[str, str]] | None = None,
    column_nullability_by_table: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[Any, ...]: ...
def infer_native_expression_source_shapes(
    *, expressions: tuple[str, ...], profile: Any
) -> tuple[dict[str, str] | None, ...]: ...
def prove_native_dynamic_contracts(
    *,
    session: NativeModelAnalysisSession | None,
    tables: Any,
    models: tuple[tuple[str, tuple[Any, ...]], ...],
) -> tuple[Any, ...]: ...
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
def semantic_shapes(*, project: Any, profile: Any | None = None) -> dict[str, dict[str, str]]: ...
def published_model_shape(
    *, model: Any, columns: dict[str, str], inputs: dict[str, dict[str, str]], profile: Any
) -> dict[str, str]: ...
def model_binding_inputs(
    model: Any, shapes: dict[str, dict[str, str]], /
) -> dict[str, dict[str, str]]: ...
def binding_relation_names(references: Sequence[Any], /) -> frozenset[str]: ...
def semantic_coverage(project: Any, /) -> dict[str, tuple[str, ...]]: ...
def source_binding_diagnostics(
    *, project: Any, columns: Mapping[str, Any], profile: Any, selected_keys: frozenset[Any]
) -> tuple[Any, ...]: ...
def known_function_names(functions: Sequence[Any], /) -> tuple[str, ...]: ...
def known_declared_types(
    *, functions: Sequence[Any], column_types: Mapping[str, Mapping[str, str]]
) -> tuple[str, ...]: ...
def complete_semantic_project(
    *,
    project: Any,
    profile: Any,
    binding_results: dict[
        str, list[tuple[str, str, int | None, int | None, int | None, int | None, str]]
    ],
    resource_sql_analysis: bool,
    session: NativeModelAnalysisSession | None = None,
) -> Any: ...
def semantic_metadata_diagnostics(
    *, project: Any, profile: Any, resource_sql_analysis: bool
) -> tuple[Any, ...]: ...

# Native analysis: contracts.
def build_audit_gate_identity(*, audits: tuple[AuditPlanEntry, ...]) -> AuditGateIdentity: ...
def evaluate_measurement(
    *,
    measured_value: float,
    sample_count: int | None,
    minimum_samples: int | None,
    thresholds: MeasurementThresholds,
) -> AuditOutcome: ...
def render_audit_sql(
    *,
    unresolved_sql: str,
    model_locations: Mapping[str, CompiledRelationLocation],
    seed_locations: Mapping[str, CompiledRelationLocation],
    source_map: Mapping[str, SourceEntry],
    adapter: BaseAdapter | None = None,
    relation_overrides: Mapping[str, str] | None = None,
) -> str: ...
def parse_audit_instances(
    *,
    raw_audits: object | None,
    file_path: Path,
    label: str,
    error_class: type[Exception],
    null_as_empty: bool,
) -> tuple[SchemaAuditInstance, ...]: ...
def optional_named_string(
    *,
    raw_value: object | None,
    file_path: Path,
    label: str,
    key: str,
    error_class: type[Exception],
) -> str | None: ...
def optional_named_bool[D: (bool, None)](
    *,
    raw_value: object | None,
    file_path: Path,
    label: str,
    key: str,
    error_class: type[Exception],
    default: D,
) -> bool | D: ...
def render_project_var_text(*, value: object, label: str) -> str: ...
def compare_contracts(
    *,
    adapter: BaseAdapter,
    connection: object,
    models: tuple[CompiledModelView, ...],
    sources: tuple[CompiledSourceView, ...],
) -> tuple[ContractEvidence, ...]: ...
def compare_contract_evidence(
    *,
    item: ContractEvidence,
    physical_columns: tuple[ColumnInfo, ...] | None,
    adapter: BaseAdapter,
) -> ContractEvidence: ...
def edit_contract_model(
    *, model: CompiledModelView, physical_columns: tuple[ColumnInfo, ...], overwrite: bool
) -> tuple[str | None, str | None]: ...
def edit_contract_source(
    *,
    source: CompiledSourceView,
    physical_columns: tuple[ColumnInfo, ...],
    overwrite: bool,
    contents: str | None = None,
) -> tuple[str | None, str | None]: ...
def remaining_contract_findings(
    *, findings: tuple[ContractFinding, ...], overwrite: bool, conflict: str | None
) -> tuple[ContractFinding, ...]: ...
def evaluate_model_contracts(
    *, project: CompiledProjectView, dialect: TypeDialect | str | None = None
) -> ContractValidationResult: ...
def promotion_conflict_diagnostics(
    *, project: CompiledProjectView, adapter_default: TablePromotionMode, settings_file: str
) -> tuple[CompilerDiagnostic, ...]: ...
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
def assemble_native_sql_tests(
    *, inputs: CompileInputsView
) -> tuple[NativeSqlTestAssembly, ...]: ...

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
def explicit_reference_report(
    project: Any,
    settings: dict[str, object],
    owners: list[tuple[Any, int, list[tuple[str, str, int]]]],
    /,
) -> PythonSqlReferenceReport: ...
def hard_coded_relation_remedy(
    *,
    owner_kind: HardCodedRelationOwnerKind,
    ref: SqlResourceRef,
    upstream_loader_by_source: Mapping[str, str] | None = None,
) -> str: ...
def old_name_reference_message(
    *, owner_label: str, written: str, method: str, model_name: str
) -> str: ...
def transitive_closure[K](
    *, start: K, edges: Mapping[K, Iterable[K]], max_depth: int | None = None
) -> frozenset[K]: ...
def transitive_closure_many[K](
    *,
    starts: Iterable[K],
    edges: Mapping[K, Iterable[K]],
    include_starts: bool,
    max_depth: int | None = None,
) -> frozenset[K]: ...
def invert_edges[K](
    *, edges: Mapping[K, Iterable[K]], sort_key: Callable[[K], Any] | None = None
) -> dict[K, tuple[K, ...]]: ...
def path_nodes[K](
    *, start: K, end: K, downstream: Mapping[K, Iterable[K]]
) -> frozenset[K] | None: ...
def attached_audit_gate_edges(
    *, project: CompiledProjectView
) -> tuple[AttachedAuditGateEdge, ...]: ...
def hook_read_edges(*, project: CompiledProjectView) -> tuple[HookReadEdge, ...]: ...
def model_python_hook_names(*, model: CompiledModelView) -> tuple[str, ...]: ...
def sql_ref_key(reference: SqlResourceRef, /) -> CompiledObjectKey: ...
def native_graph_key(key: CompiledObjectKey, /) -> tuple[str, str]: ...
def native_graph_keys(keys: Iterable[CompiledObjectKey], /) -> list[tuple[str, str]]: ...
def compiled_graph_keys(keys: Iterable[tuple[str, str]], /) -> frozenset[CompiledObjectKey]: ...
def lineage_graph_names(graph: NativeProjectGraph, /) -> dict[str, CompiledObjectKey]: ...
def lineage_graph_views(graph: NativeProjectGraph, /) -> LineageGraphViews: ...
def project_lineage_views(project: CompiledProjectView, /) -> LineageGraphViews: ...
def native_graph_from_views(
    *,
    all_keys: Mapping[str, CompiledObjectKey],
    upstream: Mapping[CompiledObjectKey, Iterable[CompiledObjectKey]],
    downstream: Mapping[CompiledObjectKey, Iterable[CompiledObjectKey]],
    tag_index: Mapping[str, Iterable[CompiledObjectKey]],
    path_index: Mapping[CompiledObjectKey, str],
) -> NativeProjectGraph: ...
def native_graph_from_edges(
    *,
    upstream: Mapping[CompiledObjectKey, Iterable[CompiledObjectKey]],
    downstream: Mapping[CompiledObjectKey, Iterable[CompiledObjectKey]],
) -> NativeProjectGraph: ...

class BindingCatalog:
    schemas: dict[str, Mapping[str, str]]
    dialect: str
    quoted_ignore_case: bool
    analysis_shapes: dict[str, tuple[Mapping[str, str], Mapping[str, str]]]
    expression_shapes: dict[str, dict[str, str] | None]
    native: NativeProjectCatalog
    def __init__(
        self,
        *,
        dialect: str,
        quoted_ignore_case: bool,
        known_functions: Sequence[str],
        known_types: Sequence[str],
        relations: Mapping[str, Mapping[str, str]],
    ) -> None: ...
    def prepare_analysis(
        self,
        *,
        types: Mapping[str, Mapping[str, str]],
        nullability: Mapping[str, Mapping[str, str]],
    ) -> None: ...
    def with_relations(self, relations: Mapping[str, Mapping[str, str]]) -> BindingCatalog: ...
    def inferred_schema(
        self, *, sql: str, columns: dict[str, str], inputs: Mapping[str, Mapping[str, str]]
    ) -> dict[str, str]: ...

def schema_validations(
    *, requests: Sequence[SqlSchemaValidationRequest]
) -> tuple[SqlBindingResult, ...]: ...
def ignores_quoted_case(*, connection: Mapping[str, object], dialect: str | None) -> bool: ...
def python_literal_sql_calls(
    source: str, start_line: int, placeholder: str
) -> list[tuple[str, str, int]]: ...
def _oracle_json_dumps(dialect_json: str, value_json: str) -> str: ...
def _oracle_text_positions(
    data: bytes, byte_offsets: list[int]
) -> tuple[str, list[tuple[int, int, int] | None]]: ...
def _oracle_yaml_load(text: str) -> str: ...
def _oracle_toml_load(text: str) -> str: ...

# Discovery: header values and authored locations.
def prepare_model_header_tokens(headers: Sequence[str], /) -> None: ...
def parse_header_values(
    *,
    header: str,
    file_path: object,
    statement_name: str,
    header_line: int | None,
    error_class: type[Exception] | None = None,
) -> dict[str, object]: ...
def model_output_column_locations(
    *, contents: str, relative_path: object, extract_implicit_alias_columns: bool = True
) -> dict[str, Any]: ...
