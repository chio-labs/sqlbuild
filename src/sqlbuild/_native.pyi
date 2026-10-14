"""Private SQLBuild native engine bindings."""

from collections.abc import Callable, Iterable, Mapping, Sequence, Set
from contextlib import AbstractContextManager
from contextvars import Token
from datetime import date, datetime
from pathlib import Path, PurePath
from typing import Any, Literal, TextIO, TypedDict, overload

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.strict_adapter import StrictAdapter
from sqlbuild.adapter.contract.models import (
    ColumnInfo,
    ExpressionInferenceProfile,
    QueryResult,
    RelationInfo,
)
from sqlbuild.adapter.contract.types import (
    AdapterExecute,
    FrameworkType,
    TablePromotionMode,
    TypeDialect,
)
from sqlbuild.adapter.relations.models import InspectionQueryRecord
from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace
from sqlbuild.cli.commands.models import (
    AuditCommandRequest,
    BuildCommandRequest,
    CheckCommandRequest,
    CloneCommandRequest,
    ContractCommandRequest,
    CostCommandRequest,
    DbtInitCommandRequest,
    DiffCommandRequest,
    FreshnessCommandRequest,
    JanitorCommandRequest,
    LineageCommandRequest,
    LoadCommandRequest,
    PlanSafetyGates,
    PlaygroundCommandRequest,
    QueryDiffPreparation,
    RefactorCommandRequest,
    ScenarioCaptureCommandRequest,
    ScenarioTestCommandRequest,
    ScopeCommandRequest,
    SeedCommandRequest,
    TestCommandRequest,
)
from sqlbuild.cli.commands.types import CompileLineageMode, ScopeIndexLoader
from sqlbuild.cli.compile.models import CompileAnalysis
from sqlbuild.cli.compile_reuse.models import CompileReuseAttempt
from sqlbuild.cli.entry.models import (
    AuthoredTargetWarehouse,
    CompileCommandRequest,
    CompileProfileFlags,
    ResolvedWarehouse,
)
from sqlbuild.cli.output.models import SkillMaintenanceResult, SkillUpdateResult, WrittenTarget
from sqlbuild.cli.progress.models import NestedProgressChildRow
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
    MacroExpansionResult,
    ModelInputBuildContext,
    NativeModelConfigInputs,
    NativeModelConfigSession,
    PythonSqlReferenceReport,
    SqlExpansionContext,
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
    DiscoveredCheckFunction,
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
    SqlTestParameterDeclaration,
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
)
from sqlbuild.compiler.lineage.types import ColumnLineageMode, InferredNullability
from sqlbuild.compiler.migrations.models import MigrationRelation
from sqlbuild.compiler.migrations.types import OldNameViewEventType
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
    CursorBounds,
    DeferralInputs,
    FutureCursorSafetyEvidence,
    MaximumStartSafetyEvidence,
    ModelPlanEntry,
    PlanOutput,
    SqlTestPlanEntry,
)
from sqlbuild.compiler.planner.types import CursorGrain
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
from sqlbuild.compiler.scopes.types import DeclarationKind, JsonValue, ScopeQueryTarget
from sqlbuild.compiler.source_freshness.models import SourceFreshnessIdentity, SourceFreshnessRecord
from sqlbuild.compiler.source_freshness.types import (
    SourceFreshnessAgeStatus,
    SourceFreshnessComparableRecord,
)
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
from sqlbuild.cost.models import CostRunRecord
from sqlbuild.cursor_algebra.models import (
    AlignedInterval,
    DateValue,
    Duration,
    TimestampValue,
)
from sqlbuild.cursor_algebra.types import Bound, BoundSentinel, CursorScalar
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.models import BuildExecutionResult, SeedExecutionResult
from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult
from sqlbuild.executor.diff.models import DiffExecutionResult
from sqlbuild.executor.janitor.models import JanitorExecutionResult, JanitorPlan
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes.models import (
    PythonCheckExecutionResult,
    PythonNodeExecutionResult,
)
from sqlbuild.executor.scenario.models import ScenarioRunResult, ScenarioSnapshotCaptureRunResult
from sqlbuild.executor.testing.models import SqlTestExecutionResult, StepResult
from sqlbuild.integrations.dbt.models import (
    DbtInteropPlan,
    DbtInteropSelectionResult,
    DbtLsNode,
    DbtManifestIndex,
    DbtManifestModel,
    DbtNodeExecutionResult,
    NormalizedDbtProfileConnection,
    ResolvedDbtProfileOutput,
)
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from sqlbuild.lint.models import HeaderSpan, LintBody, LintConfig, LintRunResult, LintViolation
from sqlbuild.lint.types import RelationKeyRow
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.presentation.models import DisplayOptions
from sqlbuild.presentation.types import CompletionState
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.rule_engine.models import Finding, Rule, RulesConfig, RulesResult
from sqlbuild.rule_engine.types import RuleCheck
from sqlbuild.runtime.contracts.models import ConnectionHooks
from sqlbuild.runtime.contracts.types import ExecutionResourceKind
from sqlbuild.runtime.observability.models import LifecycleEvent
from sqlbuild.spec.contracts.models import (
    DefaultsConfig,
    ExecutionLimitsConfig,
    LocalConfig,
    ProjectConfig,
    ScenarioConfig,
    SchemaAuditInstance,
    SchemaColumn,
    SchemaDynamicColumnFamily,
    SchemaModelEntry,
    SchemaSeedEntry,
    SettingsConfig,
    SnapshotsConfig,
    SourceEntry,
    SourceFreshnessAgePolicy,
    SourceLocation,
    TargetConfig,
)
from sqlbuild.spec.contracts.types import (
    SourceFreshnessStrategy,
    SourceFreshnessValueKind,
    WarehouseGroup,
)
from sqlbuild.sql_values.models import SqlValue
from sqlbuild.sql_values.types import StateSqlValueType

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
def builtin_rules(*, check: RuleCheck) -> list[Rule]: ...
def selected_sql_rule_codes(*, select: list[str], ignore: list[str]) -> list[str]: ...

class NativeRulesRequest:
    """A natively built rules request held until it is evaluated once."""

    def sql_facts_json(self) -> str: ...

def build_rules_request(
    project: dict[str, object],
    models: tuple[NativeCompiledProject, list[str]],
    sql_tests: list[CompiledSqlTest],
    scenarios: list[CompiledSqlScenario],
) -> NativeRulesRequest: ...
def evaluate_rules_request(
    request: NativeRulesRequest,
) -> tuple[list[Finding], list[str], int, int, int, int, bool]: ...
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

class IntegrationAssetResult:
    kind: str
    name: str
    status: str
    action: str | None
    target: str | None
    origin_relation: str | None
    staging_relation: str | None
    failed_phase: str | None
    loader: str | None
    rows_loaded: int | None
    materialized: bool | None
    future_cursor_safety: dict[str, object]
    maximum_start_safety: dict[str, object]
    microbatch: dict[str, object]
    def as_dict(self) -> dict[str, Any]: ...

class IntegrationCheckResult:
    kind: str
    name: str
    check_id: str
    passed: bool
    status: str
    dag_check_id: str | None
    severity: str | None
    asset_name: str | None
    attachment_kind: str | None
    attached_column_name: str | None
    attached_target_name: str | None
    run_scope_phase: str | None
    row_count: int | None
    reused: bool | None
    evaluation_mode: str | None
    measured_value: float | None
    sample_count: int | None
    sample_unit: str | None
    minimum_samples: int | None
    thresholds: dict[str, object] | None
    evidence_count: int | None
    evidence_truncated: bool | None
    audit_definition_name: str | None
    audit_description: str | None
    def as_dict(self) -> dict[str, Any]: ...

class IntegrationResultEnvelope:
    schema_version: int
    record_kind: str
    event_id: str
    event_sequence: int
    event_type: str
    occurred_at: str
    invocation_id: str
    run_id: str
    resource_id: str
    resource_attempt_id: str
    operation_id: str | None
    statement_id: str | None
    resource_kind: str
    resource_name: str
    attempt_number: int
    duration_ms: int | float | None
    output_kind: str
    command: str
    error_code: str | None
    error_type: str | None
    skip_code: str | None
    skip_mode: str | None
    projection_degraded: bool
    @property
    def asset(self) -> IntegrationAssetResult | None: ...
    @property
    def checks(self) -> tuple[IntegrationCheckResult, ...]: ...
    @staticmethod
    def from_json(value: str) -> IntegrationResultEnvelope: ...
    @staticmethod
    def from_json_without_optional_enrichment(value: str) -> IntegrationResultEnvelope: ...
    def to_json(self) -> str: ...

class ExecutionEventWriter:
    def __init__(self, *, path: Path | None = None) -> None: ...
    def write_build_result(
        self, *, result: object, plan: PlanOutput | None, command: str = "build"
    ) -> None: ...
    def write_clone_result(self, *, item: CloneItemResult, resource_type: str) -> None: ...
    def close(self) -> None: ...

def write_cost_run(*, project_dir: Path, record: CostRunRecord) -> Path: ...
def read_cost_run(*, project_dir: Path, run_id: str) -> CostRunRecord | None: ...
def list_cost_runs(*, project_dir: Path) -> tuple[CostRunRecord, ...]: ...
def resolve_cost_run(*, project_dir: Path, selector: str) -> CostRunRecord | None: ...
def format_cost_json(record: CostRunRecord) -> str: ...
def persist_cost_run(
    *, project_dir: Path, record: CostRunRecord, output_stream: TextIO, stage: str
) -> None: ...
def write_build_cost_breakdown(
    *, record: CostRunRecord, output_stream: TextIO, use_color: bool
) -> None: ...
def format_cost_history_json(
    *, records: tuple[CostRunRecord, ...], matching_count: int | None = None
) -> str: ...
def cost_output_payload(*, record: CostRunRecord) -> dict[str, object]: ...
def format_cost_breakdown(
    *,
    record: CostRunRecord,
    use_color: bool,
    limit: int | None = None,
    terminal_width: int | None = None,
    show_run_id: bool = True,
) -> str: ...
def format_cost_history(
    *, records: tuple[CostRunRecord, ...], matching_count: int, use_color: bool
) -> str: ...
def format_summary_footer(
    *, counts: tuple[tuple[str, int], ...], use_color: bool, elapsed: str | None = None
) -> str: ...
def format_count_noun(*, count: int, singular: str, plural: str | None = None) -> str: ...
def format_completion_line(
    *, style: CliStyle, state: CompletionState, label: str, summary: str | None = None
) -> str: ...
def format_status_cell(*, style: CliStyle, status: str, width: int = 6) -> str: ...
def format_aligned_name_value(
    *,
    plain_name: str,
    styled_name: str,
    value: str,
    name_column_width: int,
    prefix: str = "  ",
) -> str: ...
def resolve_name_column_width(
    *, names: list[str] | tuple[str, ...], min_width: int = 20
) -> int: ...
def append_overflow_line(
    *, lines: list[str], total_count: int, visible_count: int, indent: str, options: DisplayOptions
) -> list[str]: ...
def visible_entries[T](*, entries: Sequence[T], options: DisplayOptions) -> Sequence[T]: ...

class CountHeaderStyle:
    def __call__(self, text: str) -> str: ...

def count_header_style(
    *, style: CliStyle, title_style: Callable[[str], str] | None = None
) -> CountHeaderStyle: ...

class CliDocument:
    def __init__(self, style: CliStyle) -> None: ...
    def header(self, *, text: str, suffix: str | None = None) -> None: ...
    def blank(self) -> None: ...
    def field(self, *, label: str, value: str, value_padding: str = " ") -> None: ...
    def fields(
        self, *, rows: tuple[tuple[str, str], ...], label_width: int | None = None
    ) -> None: ...
    def section(self, text: str) -> None: ...
    def title_section(self, text: str) -> None: ...
    def line(self, text: str) -> None: ...
    def items(self, values: tuple[str, ...]) -> None: ...
    def command_line(self, *, prefix: str, command: str, style_command: bool = True) -> None: ...
    def commands(
        self, *, commands: tuple[str, ...], numbered: bool = False, style_command: bool = True
    ) -> None: ...
    def render(self, *, trailing_newline: bool = True) -> str: ...

def update_sqlbuild_skills(
    *,
    project_dir: Path,
    global_install: bool = False,
    requested_targets: tuple[str, ...] = (),
    force: bool = False,
    home_dir: Path | None = None,
) -> SkillUpdateResult: ...
def maintain_sqlbuild_skills(*, project_dir: Path) -> SkillMaintenanceResult: ...
def load_packaged_skill_files() -> dict[str, str]: ...
def run_skills_command(
    *,
    project_dir: Path | None,
    global_install: bool = False,
    targets: tuple[str, ...] = (),
    force: bool = False,
) -> int: ...
def run_playground_command(request: PlaygroundCommandRequest) -> int: ...
def validate_cli_warehouse(*, cli_warehouse: str | None, project_dir: Path) -> None: ...
def find_target_group_warehouse(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    selected_target: str | None,
    group: WarehouseGroup,
) -> AuthoredTargetWarehouse | None: ...
def resolve_command_warehouse(
    *,
    discovered_inputs: DiscoveredProjectInputs | None,
    selected_target: str | None,
    group: WarehouseGroup | None,
    cli_warehouse: str | None,
    connection_config: dict[str, object],
    cli_vars: dict[str, object] | None = None,
) -> ResolvedWarehouse: ...
def apply_command_warehouse(
    *,
    config: dict[str, object],
    adapter_name: str,
    project_dir: Path | None,
    discovered_inputs: DiscoveredProjectInputs | None,
    selected_target: str | None,
) -> dict[str, object]: ...
def describe_connection_warehouse(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    selected_target: str | None,
    connection_config: dict[str, object],
) -> ResolvedWarehouse: ...
def resolve_connection_config(
    *,
    raw_config: dict[str, object],
    project_dir: Path,
    adapter_name: str,
    discovered_inputs: DiscoveredProjectInputs | None = None,
    cli_vars: dict[str, object] | None = None,
    selected_target: str | None = None,
) -> dict[str, object]: ...
def resolve_project_connection_config(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    project_dir: Path,
    selected_target: str | None = None,
    cli_vars: dict[str, object] | None = None,
    require_connection: bool = True,
) -> dict[str, object]: ...
def resolve_target_connection_config(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    project_dir: Path,
    target_name: str,
    cli_vars: dict[str, object] | None = None,
) -> dict[str, object]: ...
def validate_preview_target(
    *, discovered_inputs: DiscoveredProjectInputs, as_target: str | None, command_name: str
) -> None: ...
def normalize_dbt_profile_connection(
    *, resolved: ResolvedDbtProfileOutput
) -> NormalizedDbtProfileConnection: ...
def build_dbt_init_project_toml(
    *,
    project_name: str,
    adapter: str,
    target_name: str,
    profile_name: str,
    dbt_project_dir: str,
    profiles_dir: str,
    target_path: str,
    target_schema: str | None,
    target_database: str | None,
) -> str: ...
def load_dbt_manifest_index(*, manifest_path: Path) -> DbtManifestIndex: ...
def build_compile_dbt_manifest_index(
    *, manifest_contents: str | None
) -> DbtManifestIndex | None: ...
def build_dbt_manifest_index(*, raw_data: object) -> DbtManifestIndex: ...
def resolve_dbt_manifest_model(
    *, manifest: DbtManifestIndex, name: str, package_name: str | None = None
) -> DbtManifestModel: ...
def validate_compile_dbt_model_names(
    *, known_model_names: Iterable[str], dbt_manifest: DbtManifestIndex | None
) -> None: ...
def validate_compile_dbt_model_reference(
    *,
    reference: CompileSqlReference,
    model_relative_path: Path,
    dbt_manifest: DbtManifestIndex | None,
) -> None: ...
def resolve_sqlbuild_model_dbt_refs(
    *,
    project: CompiledProjectView,
    manifest: DbtManifestIndex,
    selected_model_names: Iterable[str] | None = None,
) -> tuple[tuple[CompiledModelView, DbtManifestModel], ...]: ...

class DbtCombinedGraph:
    @property
    def nodes(self) -> frozenset[str]: ...
    @property
    def upstream_deps(self) -> dict[str, tuple[str, ...]]: ...
    @property
    def downstream_deps(self) -> dict[str, tuple[str, ...]]: ...
    def downstream_sqlbuild_model_names(self, unique_ids: Iterable[str]) -> tuple[str, ...]: ...

def build_dbt_combined_graph(
    *, manifest: DbtManifestIndex, project: CompiledProjectView
) -> DbtCombinedGraph: ...
def resolve_dbt_interop_sqlbuild_selection(
    *,
    project: CompiledProjectView,
    graph: DbtCombinedGraph,
    select: Sequence[str],
    manifest: DbtManifestIndex | None = None,
    exclude: Sequence[str] | None = None,
    dbt_anchor_unique_ids_by_term: Mapping[str, Sequence[str]] | None = None,
) -> DbtInteropSelectionResult: ...
def dbt_fqn_selector_term(*, fqn: Sequence[str], fallback: str) -> str: ...
def resolve_dbt_reference_relation(
    *,
    manifest: DbtManifestIndex | None,
    ref_kind: str,
    ref_name: str,
    ref_package: str | None,
) -> str | None: ...
def build_dbt_interop_plan(
    *,
    command: DbtInteropCommand | str,
    dbt_command_argv: Sequence[str],
    dbt_ls_nodes: Sequence[DbtLsNode],
    sqlbuild_command_argvs: Sequence[Sequence[str]],
    selection: DbtInteropSelectionResult,
    dbt_required_selector_terms: Sequence[str] = (),
    supplemental_dbt_command_argvs: Sequence[Sequence[str]] = (),
    warnings: Sequence[str] = (),
    sqlbuild_plan_output: PlanOutput | None = None,
) -> DbtInteropPlan: ...
def render_dbt_interop_plan(
    *,
    plan: DbtInteropPlan,
    json_output: bool,
    use_color: bool,
    display_options: DisplayOptions | None = None,
) -> str: ...
def run_debug_command(
    *,
    project_dir: Path | None = None,
    no_color: bool = False,
    no_connection: bool = False,
    selected_target: str | None = None,
    json_output: bool = False,
) -> int: ...

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

class NativeProgressProjector:
    def __init__(self, *, stream: TextIO, use_color: bool, debug: bool = False) -> None: ...
    def install(self) -> Token[NativeProgressProjector | None]: ...
    def restore(self, token: Token[NativeProgressProjector | None]) -> None: ...
    def configure_resources(self, *, ordinals: Mapping[str, int], total: int) -> None: ...
    def expect_resource_enrichment(self, *, resource_name: str) -> None: ...
    def is_operation_active(self, *, operation_name: str) -> bool: ...
    def consume(self, event: LifecycleEvent) -> None: ...
    def consume_resource_terminal(
        self,
        *,
        resource_name: str,
        resource_id: str | None = None,
        resource_attempt_id: str | None = None,
        attempt_number: int | None = None,
    ) -> float | None: ...
    def resource_terminal_duration(
        self,
        *,
        resource_name: str,
        resource_id: str | None = None,
        resource_attempt_id: str | None = None,
        attempt_number: int | None = None,
    ) -> float | None: ...
    def close(self) -> None: ...

def render_diff_output(
    *,
    result: DiffExecutionResult,
    from_label: str,
    to_label: str,
    mode_label: str,
    use_color: bool,
    verbose: bool,
    max_column_examples: int,
    max_row_only_examples: int,
    max_value_length: int | None = ...,
    suppress_example_values: bool = ...,
    outcome: str | None = ...,
) -> str: ...
def render_diff_error_json(
    *,
    status: str,
    code: str,
    message: str,
    help_text: str | None = ...,
    size_guard: dict[str, object] | None = ...,
) -> str: ...
def run_diff_command(*, request: DiffCommandRequest) -> int: ...
def execute_query_diff(
    *, request: DiffCommandRequest, preparation: QueryDiffPreparation
) -> DiffExecutionResult: ...
def machine_output_mode(args: CliNamespace, /) -> bool: ...
def current_native_progress_projector() -> NativeProgressProjector | None: ...

class ConnectionProgressReporter:
    def __init__(
        self,
        *,
        adapter_name: str,
        stream: TextIO,
        blank_line_before_start: bool = False,
        blank_line_after_complete: bool = False,
        use_color: bool = False,
    ) -> None: ...
    def on_connection_start(self, connection_count: int) -> None: ...
    def on_connection_complete(self, *, connection_count: int, elapsed_seconds: float) -> None: ...
    def on_connection_error(self, *, connection_count: int, elapsed_seconds: float) -> None: ...

class DbtEventStreamUpdate:
    @property
    def status_message(self) -> str | None: ...
    @property
    def result(self) -> DbtNodeExecutionResult | None: ...
    @property
    def row(self) -> str | None: ...
    @property
    def finished(self) -> bool: ...

class DbtEventStream:
    def __init__(
        self,
        *,
        display_total: int | None,
        detail_by_unique_id: Mapping[str, str] | None,
        use_color: bool,
    ) -> None: ...
    def consume(self, line: str) -> DbtEventStreamUpdate | None: ...

def render_dbt_node_result(
    *,
    result: DbtNodeExecutionResult,
    use_color: bool,
    display_index: int | None = None,
    display_total: int | None = None,
    detail: str = "",
) -> str: ...
def format_dbt_active_node_status(
    *, active_nodes: Sequence[tuple[str, float]], now: float
) -> str: ...

class PlanningProgressReporter:
    def __init__(self, *, stream: TextIO, use_color: bool = False) -> None: ...
    def on_progress(self, message: str) -> None: ...
    def start(self, message: str) -> None: ...
    def update(self, message: str) -> None: ...
    def complete(self, message: str) -> None: ...
    def complete_styled(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...
    def finish(self, *, blank_line_after: bool = False) -> None: ...

class VerboseInspectionWriter:
    def __init__(self) -> None: ...
    def write(self, record: InspectionQueryRecord) -> None: ...
    def write_total(self) -> None: ...
    @staticmethod
    def format_record(*, record: InspectionQueryRecord) -> str: ...

def format_execution_header(*, command: str, target: str | None, concurrency: int) -> str: ...
def write_execution_header(
    *, stream: TextIO, command: str, target: str | None, concurrency: int, use_color: bool
) -> None: ...
def format_expectation_name(model_name: str) -> str: ...
def format_expectation_detail(step_result: StepResult) -> str: ...
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

def finalize_rule_findings_rows(request: dict[str, object]) -> list[Finding]: ...
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
def neutralize_lint_interpolation(
    body: str, dialect: str, for_formatting: bool = False
) -> tuple[str, list[tuple[str, int, int, int, int, str]]]: ...
def neutralize_lint_context_interpolation(
    body: str,
) -> tuple[str, list[tuple[str, int, int, int, int, str]]]: ...
def neutralize_lint_audit_parameters(
    body: str,
) -> tuple[str, list[tuple[str, int, int, int, int, str]]]: ...
def restore_lint_interpolation(
    fixed: str, sites: list[tuple[str, int, int, int, int, str]]
) -> tuple[bool, str]: ...
def lint_interpolation_text_at(body: str, start: int, dialect: str) -> str | None: ...
def scan_fixture_typed_null_candidates(
    project_dir: Path, selected_paths: frozenset[Path] | None = None
) -> tuple[frozenset[Path], frozenset[str]]: ...
def format_lint_sql_bodies(
    files: list[tuple[Path, str]], project_dir: Path, config: LintConfig
) -> tuple[dict[Path, str], list[LintViolation]]: ...
def lint_native_sql_bodies(
    bodies: list[LintBody], contents_by_path: dict[Path, str], config: LintConfig
) -> list[LintViolation]: ...
def apply_lint_suppressions(
    violations: list[LintViolation],
    contents_by_path: dict[Path, str],
    allow_suppressions: bool,
) -> list[LintViolation]: ...
def load_rules_config(*, project_dir: Path) -> RulesConfig: ...
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
def run_scope_command(
    *,
    request: ScopeCommandRequest,
    load_scope_index: ScopeIndexLoader | None = None,
    output_stream: TextIO | None = None,
) -> int: ...
def render_scope_result(
    *,
    result: ScopeReport | ScopeBrowseResult | ScopeListResult,
    request: ScopeCommandRequest,
    use_color: bool = False,
) -> str: ...
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
def load_project_config_file(project_dir: Path, /) -> ProjectConfig: ...
def load_local_config_file(project_dir: Path, /) -> LocalConfig: ...
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
def find_macro_call_names(sql: str, /) -> tuple[str, ...]: ...
def expand_sql_macros(
    *,
    sql: str,
    file_path: Path,
    loaded_macros: dict[str, LoadedMacro],
    macro_context: MacroContext,
    macro_overrides: dict[str, str] | None = None,
    declaration_resolver: DeclarationScopeResolver | None = None,
    declarations: DeclarationResolutionContext | None = None,
    consumer: ResourceIdentity | DeclarationIdentity | None = None,
) -> MacroExpansionResult: ...
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
def lineage_cache_fingerprint(
    *, project_dir: Path, cli_vars: dict[str, object] | None
) -> str | None: ...
def run_lineage_command(*, request: LineageCommandRequest) -> int: ...
def run_refactor_command(*, request: RefactorCommandRequest) -> int: ...
def run_janitor_command(*, request: JanitorCommandRequest) -> int: ...
def run_freshness_command(*, request: FreshnessCommandRequest) -> int: ...
def run_clone_command(*, request: CloneCommandRequest) -> int: ...
def run_load_command(*, request: LoadCommandRequest) -> int: ...
def run_check_command(*, request: CheckCommandRequest) -> int: ...
def write_check_results(
    *,
    stream: TextIO,
    results: tuple[PythonCheckExecutionResult, ...],
    use_color: bool,
    check_functions: tuple[DiscoveredCheckFunction, ...] = (),
    python_graph: PythonNodeGraph | None = None,
) -> None: ...
def format_check_json(*, results: tuple[PythonCheckExecutionResult, ...]) -> str: ...
def run_test_command(*, request: TestCommandRequest) -> int: ...
def run_seed_command(*, request: SeedCommandRequest) -> int: ...
def run_build_command(*, request: BuildCommandRequest) -> int: ...
def enforce_plan_safety_policies(
    *,
    plan: PlanOutput,
    gates: PlanSafetyGates,
    snapshots_config: SnapshotsConfig,
    target_name: str | None,
    execution_limits: ExecutionLimitsConfig,
    streams: tuple[TextIO, TextIO],
) -> None: ...
def enforce_model_execution_limit(
    *,
    model_count: int,
    target_name: str | None,
    limits: ExecutionLimitsConfig,
    refusal_note: str,
) -> None: ...
def run_audit_command(*, request: AuditCommandRequest) -> int: ...
def run_contract_command(*, request: ContractCommandRequest) -> int: ...
def run_init_command(project_dir: Path | None = None) -> int: ...
def run_cost_command(request: CostCommandRequest) -> int: ...
def run_dbt_command(
    *, command: DbtInteropCommand, project_dir: Path | None, args: tuple[str, ...], no_color: bool
) -> int: ...
def run_dbt_init_command(request: DbtInitCommandRequest) -> int: ...
def refresh_pending_cost_run(request: CostCommandRequest) -> None: ...
def parse_cost_since_bound(*, value: str | None) -> datetime | None: ...
def run_query_command(
    *,
    project_dir: Path | None,
    sql: str | None,
    query_file: Path | None = None,
    selected_target: str | None = None,
    output_format: str = "long",
    limit: int | None = 20,
) -> int: ...
def render_query_result(*, result: QueryResult, output_format: str, limit: int | None) -> str: ...
def run_dag_command(
    *,
    project_dir: Path | None,
    no_sql_validation: bool = False,
    json_output: bool = False,
    cli_vars: dict[str, object] | None = None,
) -> int: ...
def run_scenario_test_command(*, request: ScenarioTestCommandRequest) -> int: ...
def run_scenario_capture_command(*, request: ScenarioCaptureCommandRequest) -> int: ...
def sql_analysis_off_guidance(
    *, discovered_inputs: DiscoveredProjectInputs, purpose: str
) -> tuple[str, str] | None: ...
def serialize_hook_entries(
    *,
    value: object,
    sql_fields: tuple[str, ...],
    python_hook_fields: Mapping[str, Mapping[str, object]] | None = None,
) -> list[dict[str, object]]: ...
def named_declaration_role_kind(*, relative_path: PurePath) -> DeclarationKind | None: ...
def discover_model_description_inputs(*, project_dir: Path) -> DiscoveredProjectInputs: ...
def microbatch_guidance() -> tuple[str, str]: ...
def explicit_references_help(*, allowed: str) -> str: ...
def run_format_command(
    *,
    project_dir: Path | None,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    check: bool = False,
    diff: bool = False,
    fixtures_only: bool = False,
    fix: bool = False,
    json_output: bool = False,
    no_color: bool = False,
) -> int: ...
def format_parameterized_test_label(
    *,
    name: str,
    source_path: Path | None,
    parameter_schema: tuple[SqlTestParameterDeclaration, ...],
    parameter_values: tuple[tuple[str, SqlValue], ...],
) -> str: ...
def resolve_test_name_width(test_entries: tuple[SqlTestPlanEntry, ...]) -> int: ...
def build_test_expectation_rows(
    result: SqlTestExecutionResult,
) -> tuple[NestedProgressChildRow, ...]: ...
def select_load_entries(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    target_config: TargetConfig | None,
    loader_default_database: str | None = None,
    loader_default_schema: str | None = None,
) -> tuple[SourceEntry, ...]: ...
def select_load_reference_entries(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    selected_sources: tuple[SourceEntry, ...],
    target_config: TargetConfig | None,
    loader_default_database: str | None = None,
    loader_default_schema: str | None = None,
) -> tuple[SourceEntry, ...]: ...
def resolve_loader_defaults(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    selected_target: str | None = None,
    target_config: TargetConfig | None = None,
    cli_vars: dict[str, object] | None = None,
) -> tuple[str | None, str | None]: ...

class LoadProgressReporter:
    def __init__(
        self, *, stream: TextIO, use_color: bool, source_order: dict[str, int], total_count: int
    ) -> None: ...
    def on_start(self, source: SourceEntry) -> None: ...
    def on_progress(self, source: SourceEntry, message: str) -> None: ...
    def on_complete(self, result: LoadExecutionResult) -> None: ...
    def clear_transient_line(self) -> None: ...
    def redraw_transient_line(self) -> None: ...

def observe_source_freshness_json(
    *,
    adapter: object,
    connection: object,
    sources: Sequence[SourceEntry],
    observed_at: datetime,
    select: Sequence[str] = (),
    exclude: Sequence[str] = (),
    run_id: str | None = None,
    previous_records: Mapping[SourceFreshnessIdentity, SourceFreshnessRecord] | None = None,
    previous_records_by_source_name: Mapping[str, SourceFreshnessRecord] | None = None,
) -> str: ...
def render_janitor_plan(*, plan: JanitorPlan, use_color: bool = False) -> str: ...
def render_janitor_completion(
    *, result: JanitorExecutionResult, use_color: bool = False
) -> str: ...

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
def resolve_python_node_selection(
    *, graph: PythonNodeGraph, select: Sequence[str], exclude: Sequence[str]
) -> frozenset[str]: ...
def resolve_python_check_excludes(
    *, graph: PythonNodeGraph, exclude: Sequence[str]
) -> frozenset[str]: ...
def resolve_python_sql_run_selection(
    *,
    project_graph: ProjectGraph,
    python_graph: PythonNodeGraph,
    select: Sequence[str],
    exclude: Sequence[str],
) -> tuple[list[tuple[str, str]], list[str]]: ...
def python_node_graph_indexes(
    nodes: list[tuple[str, tuple[str, ...], str, list[str]]], /
) -> tuple[
    list[tuple[str, str]],
    list[tuple[str, list[str]]],
    list[tuple[str, list[str]]],
    list[tuple[str, list[str]]],
    list[tuple[str, str]],
]: ...
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
def deterministic_migration_event_id(
    *,
    run_id: str,
    target_name: str | None,
    origin: MigrationRelation,
    destination: MigrationRelation,
) -> str: ...
def deterministic_column_migration_event_id(
    *,
    run_id: str,
    target_name: str | None,
    relation: MigrationRelation,
    origin_column: str,
    destination_column: str,
) -> str: ...
def deterministic_old_name_view_event_id(
    *, event_type: OldNameViewEventType, migration_event_id: str
) -> str: ...
def render_event_exists_sql(*, table: str, event_id: str) -> str: ...
def render_event_insert_sql(
    *,
    table: str,
    columns: tuple[str, ...],
    column_types: Mapping[str, StateSqlValueType],
    values: tuple[object | None, ...],
) -> str: ...
def source_freshness_data_version_hash(
    *,
    source_name: str,
    strategy: SourceFreshnessStrategy | str,
    value_kind: SourceFreshnessValueKind | str,
    data_version: str,
) -> str: ...
def normalize_source_freshness_data_version(
    *, value: object, value_kind: SourceFreshnessValueKind
) -> str: ...
def source_freshness_records_equivalent(
    *,
    previous_record: SourceFreshnessComparableRecord,
    current_record: SourceFreshnessComparableRecord,
    lag_tolerance: str | None = None,
) -> bool: ...
def evaluate_source_freshness_age_policy(
    *,
    policy: SourceFreshnessAgePolicy | None,
    data_version: object,
    observed_at: datetime,
) -> SourceFreshnessAgeStatus | None: ...
def redact_diagnostic_text(value: str) -> str: ...
def redact_diagnostic_value(*, name: str, value: object) -> object: ...
def sql_rule_lint_key(*, config: LintConfig) -> str: ...
def sql_model_rule_keys(
    *, lint_key: str, codes: list[str], models: list[tuple[str, str, str, str | None]]
) -> dict[str, str]: ...
def sql_file_rule_key(
    *, lint_key: str, codes: list[str], relative_path: str, contents: str, expanded: bool
) -> str | None: ...
def load_sql_rule_cache(*, path: Path) -> dict[str, tuple[str, str]]: ...
def lookup_sql_rule_cache(
    *, entries: dict[str, tuple[str, str]], keys: list[tuple[str, str]]
) -> dict[str, list[Finding]]: ...
def encode_sql_rule_findings(*, findings: list[Finding]) -> str: ...
def write_sql_rule_cache(*, path: Path, entries: dict[str, tuple[str, str]]) -> None: ...
def cursor_parse(*, raw: object, cursor_type: str) -> CursorScalar: ...
def cursor_try_parse(*, raw: object, cursor_type: str) -> CursorScalar | None: ...
def cursor_render(*, value: CursorScalar) -> str: ...
def cursor_sentinel_to_token(*, sentinel: Bound) -> str: ...
def cursor_sentinel_from_token(*, token: str) -> BoundSentinel | None: ...
def cursor_compare(*, left: CursorScalar, right: CursorScalar) -> int: ...
def cursor_sort_key(*, raw: object, cursor_type: str) -> datetime | int: ...
def cursor_max_bound[T](*, values: tuple[T, ...] | list[T], cursor_type: str) -> T: ...
def cursor_min_bound[T](*, values: tuple[T, ...] | list[T], cursor_type: str) -> T: ...
def cursor_floor_to_grain(*, value: CursorScalar, grain: CursorGrain) -> CursorScalar: ...
def cursor_next_boundary(*, value: CursorScalar, grain: CursorGrain) -> CursorScalar: ...
def cursor_inclusive_to_exclusive(
    *, value: CursorScalar, grain: CursorGrain | None
) -> CursorScalar: ...
def cursor_exclusive_to_inclusive(
    *, value: CursorScalar, grain: CursorGrain | None
) -> CursorScalar: ...
def cursor_exclusive_end_from_observed_max(
    *, value: CursorScalar, grain: CursorGrain | None
) -> CursorScalar: ...
def cursor_observed_partition(
    *, value: CursorScalar, grain: CursorGrain | None
) -> AlignedInterval: ...
def cursor_clamp(
    *, interval: AlignedInterval, bounds: AlignedInterval
) -> AlignedInterval | None: ...
def cursor_merge(*, intervals: tuple[AlignedInterval, ...]) -> tuple[AlignedInterval, ...]: ...
def cursor_split_into_batches(
    *, interval: AlignedInterval, step: int
) -> tuple[AlignedInterval, ...]: ...
def cursor_cap_from_start[T](*, intervals: tuple[T, ...], count: int) -> tuple[T, ...]: ...
def cursor_cap_from_end[T](*, intervals: tuple[T, ...], count: int) -> tuple[T, ...]: ...
def validate_cursor_interval(
    *, start: CursorScalar, end: CursorScalar, grain: CursorGrain | None
) -> None: ...
def parse_cursor_duration(value: str) -> tuple[int, int, int, int, int, int] | None: ...
def shift_by_cursor_duration[M: date](*, moment: M, duration: Duration, direction: int) -> M: ...
def get_config_str(*, values: Mapping[str, object], key: str) -> str | None: ...
def get_config_bool(*, values: Mapping[str, object], key: str) -> bool | None: ...
def get_config_int(*, values: Mapping[str, object], key: str) -> int | None: ...
def get_config_string_tuple(
    *, values: Mapping[str, object], key: str
) -> tuple[str, ...] | None: ...
def get_config_cursor_bound(*, values: Mapping[str, object], key: str) -> str | None: ...
def custom_rule_import_closure(*, rule: Rule, project_dir: Path) -> tuple[Path, ...]: ...
def custom_rule_implementation_fingerprint(
    *, rule: Rule, project_dir: Path, import_closure: tuple[Path, ...] | None = None
) -> str: ...
def custom_rule_identity(
    *,
    code_identity: str,
    runtime_version: str,
    code: str,
    family: str,
    slug: str,
    message: str,
    remediation: str,
    subject: str | None,
    implementation_fingerprint: str,
    config: RulesConfig,
    dialect: str,
    project_dir: str,
) -> str: ...

class CustomRuleCache:
    """One custom-rule run's subjects, reused and new results, and its cache file."""

    def __init__(
        self,
        *,
        path: Path | None,
        rules: list[tuple[str, str | None, str | None]],
        target_name: str | None,
        models: list[tuple[str, str, str | None]],
    ) -> None: ...
    def pending_readsets(self) -> list[tuple[tuple[str, ...], ...]]: ...
    def plan(self, *, digests: list[str | None]) -> dict[str, list[str] | None]: ...
    def record(
        self,
        *,
        evaluated: list[
            tuple[
                str,
                str,
                tuple[tuple[tuple[str, ...], ...], str | None] | None,
                list[dict[str, object]],
            ]
        ],
    ) -> None: ...
    def findings(self) -> list[Finding]: ...
    @property
    def hits(self) -> int: ...
    @property
    def misses(self) -> int: ...

def custom_rule_test_evidence(
    *, rule: Rule, project_dir: Path
) -> list[tuple[str, int, int, str]]: ...
def format_rules_result(*, result: RulesResult, json_output: bool) -> str: ...
def with_duplicate_literal_hints(
    *, findings: tuple[Finding, ...], project_dir: Path
) -> tuple[Finding, ...]: ...
def scan_headers(*, contents: str, first_only: bool = False) -> tuple[HeaderSpan, ...]: ...
def sql_body_ranges(
    *, contents: str, headers: tuple[HeaderSpan, ...]
) -> tuple[tuple[int, int], ...]: ...
def measurement_body_ranges(*, contents: str) -> tuple[tuple[int, int], ...]: ...
def run_lint(
    *,
    project_dir: Path,
    config: LintConfig,
    value_renderer: TypedSqlValueRenderer | None = None,
    selected_paths: frozenset[Path] | None = None,
    discovered_inputs: DiscoveredProjectInputs | None = None,
    dynamic_output_paths: frozenset[Path] = frozenset(),
    compiled_expansions: dict[Path, CompiledSqlExpansion] | None = None,
    expansion_context: SqlExpansionContext | None = None,
    source_files: dict[Path, str] | None = None,
    skip_unexpandable: bool = False,
) -> LintRunResult: ...
def collect_lint_project_files(
    *, project_dir: Path, selected_paths: frozenset[Path] | None = None
) -> dict[Path, str]: ...
def lint_native_headers(
    *, contents: str, file_path: Path, headers: tuple[HeaderSpan, ...], config: LintConfig
) -> tuple[LintViolation, ...]: ...
def format_native_headers(
    *, contents: str, file_path: Path, config: LintConfig
) -> tuple[str, tuple[LintViolation, ...]]: ...
def prepare_native_header_cache(*, files: dict[Path, str]) -> None: ...
def safe_format_files(
    *, files: dict[Path, str], config: LintConfig
) -> tuple[dict[Path, str], dict[Path, str]]: ...
def reject_unparseable_header_rewrites(
    *, updated: dict[Path, str], config: LintConfig, faults: list[LintViolation]
) -> tuple[dict[Path, str], list[LintViolation]]: ...
def external_identifiers_for_headers(
    *, contents: str, headers: tuple[HeaderSpan, ...]
) -> tuple[str, ...]: ...
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
def inclusive_cursor_end(*, end: str, cursor_type: str | None, cursor_grain: str | None) -> str: ...
def resolve_bounded_cursor_override(
    *,
    start_cursor_override: str | None,
    end_cursor_override: str | None,
    cursor_type: str | None,
    cursor_grain: str | None,
) -> CursorBounds | None: ...
def cursor_bound_display(
    *, value: str, cursor_type: str | None, cursor_grain: str | None
) -> str: ...
def model_materialization_label(entry: ModelPlanEntry) -> str: ...
def model_resource_type(entry: ModelPlanEntry | None) -> str: ...
def model_execution_annotation(entry: ModelPlanEntry | None) -> str: ...
def materialization_type_display(resource_kind: ExecutionResourceKind) -> str: ...
def format_no_input_rows(input_names: tuple[str, ...]) -> str: ...
def format_waiting_on_empty_inputs(input_names: tuple[str, ...]) -> str: ...
def resolve_effective_microbatch_batch_size(*, batch_size: str, effective_grain: str) -> str: ...
def aligned_timestamp_bounds(
    *, start: DateValue | TimestampValue, end: DateValue | TimestampValue
) -> tuple[datetime, datetime]: ...
