"""Structured runtime models for project compilation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.compiler.auditing.models import MeasurementContract, MeasurementThresholds
from sqlbuild.compiler.auditing.types import AuditEvaluationMode, AuditSeverity
from sqlbuild.compiler.compile.constants import DEFAULT_SQL_TEST_MODE
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
    FunctionLanguage,
    SqlTestMode,
    TypedSqlValueRenderer,
)
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredAuditBlock,
    DiscoveredAuditFile,
    DiscoveredHookFunction,
    DiscoveredLoaderFunction,
    DiscoveredMaterializationFile,
    DiscoveredProjectInputs,
    DiscoveredPythonFunctionFile,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
    DiscoveredSqlFunctionFile,
    DiscoveredSqlHookFile,
    DiscoveredSqlModelFile,
    DiscoveredSqlScenarioFile,
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestFile,
    EnumDeclaration,
    ModelSchemaDeclaration,
    SqlTestParameterDeclaration,
)
from sqlbuild.compiler.lineage.types import (
    ColumnLineageConfidence,
    ColumnTransformKind,
    InferredNullability,
)
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver, SqlReferenceKind
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    GrantRecord,
    ResourceIdentity,
    ScopeIndex,
    ScopeLookup,
    UsageRecord,
    VisibilityRecord,
)
from sqlbuild.spec.contracts.models import (
    LocalConfig,
    ProjectConfig,
    ResolvedTableType,
    ResolvedTimeTravelRetention,
    ScenarioConfig,
    SchemaModelEntry,
    SchemaSeedEntry,
    SettingsConfig,
    SourceEntry,
    SourceLocation,
    TargetConfig,
)
from sqlbuild.sql_values.models import SqlValue
from sqlbuild.sql_values.types import CollectionRendering


@dataclass(frozen=True)
class RelatedLocation:
    """A secondary authored location that adds context to a diagnostic."""

    label: str
    location: SourceLocation
    message: str | None = None


@dataclass(frozen=True)
class CompilerDiagnostic:
    """One project diagnostic produced by compile-time checks."""

    phase: DiagnosticPhase | str
    severity: DiagnosticSeverity | str
    code: str
    message: str
    resource_type: CompiledResourceType | str | None = None
    resource_name: str | None = None
    column_name: str | None = None
    path: Path | None = None
    line: int | None = None
    column: int | None = None
    location: SourceLocation | None = None
    related_locations: tuple[RelatedLocation, ...] = field(default_factory=tuple)
    help: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "phase", DiagnosticPhase(self.phase))
        object.__setattr__(self, "severity", DiagnosticSeverity(self.severity))
        if self.resource_type is not None:
            object.__setattr__(
                self,
                "resource_type",
                CompiledResourceType(self.resource_type),
            )
        if (
            self.location is None
            and self.path is not None
            and self.line is not None
            and self.column is not None
        ):
            object.__setattr__(
                self,
                "location",
                SourceLocation(path=self.path, line=self.line, column=self.column),
            )
        if self.location is not None:
            object.__setattr__(self, "path", self.location.path)
            object.__setattr__(self, "line", self.location.line)
            object.__setattr__(self, "column", self.location.column)

    @property
    def is_error(self) -> bool:
        """Return whether this diagnostic should fail the command."""

        return self.severity == DiagnosticSeverity.ERROR


@dataclass(frozen=True)
class InferredColumn:
    """One output column inferred from query SQL via sql_analysis parsing."""

    name: str
    type: str | None = None
    nullability: InferredNullability = InferredNullability.UNKNOWN


@dataclass(frozen=True)
class CompileModelConfig:
    """Pre-semantic effective config layers attached to a model input."""

    values: dict[str, object] = field(default_factory=dict)
    matched_path_default: str | None = None
    logical_schema: str | None = None
    logical_database: str | None = None
    time_travel_retention: ResolvedTimeTravelRetention = field(
        default_factory=ResolvedTimeTravelRetention
    )
    table_type: ResolvedTableType = field(default_factory=ResolvedTableType)


@dataclass(frozen=True)
class CursorInputRoles:
    """Effective filter and watermark inputs for one compiled model."""

    filter_inputs: dict[str, str]
    watermark_inputs: dict[str, str]
    filter_field: str
    watermark_field: str
    uses_legacy_alias: bool


@dataclass(frozen=True)
class LoadedMacro:
    """One loaded project macro available for compile-time SQL expansion."""

    name: str
    file_path: Path
    relative_path: Path
    raw_source: str
    function: Callable[..., object]
    dependencies: tuple[DeclarationIdentity, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class StaticMacroExport:
    """Value-free AST inventory for one project-owned macro export."""

    name: str
    relative_path: Path
    parameters: tuple[str, ...]
    line: int
    source_digest: str
    dependencies: tuple[DeclarationIdentity, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class StaticMacroFault:
    """One value-free static macro inventory fault."""

    relative_path: Path
    message: str


@dataclass(frozen=True)
class StaticMacroInventory:
    """AST macro exports and faults collected without module execution."""

    exports: tuple[StaticMacroExport, ...] = field(default_factory=tuple)
    faults: tuple[StaticMacroFault, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScopeRelationshipFault:
    """One test or scenario relationship extraction fault."""

    relative_path: Path
    message: str


@dataclass(frozen=True)
class ScopeRelationshipBuild:
    """Expected-model grants and independently retained relationship faults."""

    grants: tuple[GrantRecord, ...] = field(default_factory=tuple)
    faults: tuple[ScopeRelationshipFault, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DeclarationRuntimeProjection:
    """Process-only declaration values keyed by canonical static identity."""

    declarations: Mapping[
        DeclarationIdentity, EnumDeclaration | ConstantDeclaration | LoadedMacro
    ] = field(default_factory=dict)


@dataclass(frozen=True)
class DeclarationScopeResolver:
    """Process-only lookup state used to project visible runtime declarations."""

    project_dir: Path | None
    lookup: ScopeLookup
    projection: DeclarationRuntimeProjection


@dataclass(frozen=True)
class DeclarationScopeBuild:
    """Static artifact and process-local values shared by compile attachment phases."""

    loaded_macros: dict[str, LoadedMacro]
    index: ScopeIndex
    resolver: DeclarationScopeResolver


@dataclass(frozen=True)
class MacroContext:
    """Compile-time context passed to adapter-aware SQL macros."""

    adapter_name: str
    sql_analysis_enabled: bool
    target_name: str | None
    vars: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MacroExpansionResult:
    """Expanded SQL and resolved macro usage facts from one authored string."""

    sql: str
    spans: tuple[ExpansionSpan, ...] = field(default_factory=tuple)
    dependencies: tuple[DeclarationIdentity, ...] = field(default_factory=tuple)
    usages: tuple[UsageRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DeclarationExpansionResult:
    """Expanded SQL and resolved declaration usage facts from one authored string."""

    sql: str
    spans: tuple[ExpansionSpan, ...] = field(default_factory=tuple)
    usages: tuple[UsageRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AuthoredSqlExpansionResult:
    """Fully expanded authored SQL with all resolved declaration usages."""

    sql: str
    usages: tuple[UsageRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class HookExpansionResult:
    """Expanded model hook values and declaration usage facts."""

    values: dict[str, object]
    usages: tuple[UsageRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DeclarationResolutionContext:
    """Declarations visible during one authored SQL expansion."""

    enums: dict[str, EnumDeclaration] = field(default_factory=dict)
    constants: dict[str, ConstantDeclaration] = field(default_factory=dict)
    inaccessible_enums: dict[str, DeclarationRecord] = field(default_factory=dict)
    inaccessible_constants: dict[str, DeclarationRecord] = field(default_factory=dict)
    enum_visibility: dict[str, tuple[VisibilityRecord, ...]] = field(default_factory=dict)
    constant_visibility: dict[str, tuple[VisibilityRecord, ...]] = field(default_factory=dict)
    macros: dict[str, LoadedMacro] = field(default_factory=dict)
    macro_records: dict[str, DeclarationRecord] = field(default_factory=dict)
    inaccessible_macros: dict[str, DeclarationRecord] = field(default_factory=dict)
    consumer: ResourceIdentity | DeclarationIdentity | None = None


@dataclass(frozen=True)
class DeclarationExpansionContext:
    """Declarations and adapter rendering used by one authored SQL owner."""

    declarations: DeclarationResolutionContext
    value_renderer: TypedSqlValueRenderer
    collection_rendering: CollectionRendering
    resolver: DeclarationScopeResolver | None = None


@dataclass(frozen=True)
class CompileAdapterContext:
    """Cycle-free adapter behavior required while building compile inputs."""

    value_renderer: TypedSqlValueRenderer
    collection_rendering: CollectionRendering
    python_functions_inherit_default_namespace: bool


@dataclass(frozen=True)
class ModelInputBuildContext:
    """Run-constant config and macros for building model compile inputs."""

    effective_vars: dict[str, object]
    effective_settings: SettingsConfig
    target_config: TargetConfig | None
    effective_target_name: str | None
    run_id: str
    macro_context: MacroContext
    loaded_macros: dict[str, LoadedMacro]
    value_renderer: TypedSqlValueRenderer
    collection_rendering: CollectionRendering
    public_enums: dict[str, EnumDeclaration] = field(default_factory=dict)
    public_constants: dict[str, ConstantDeclaration] = field(default_factory=dict)
    public_model_schemas: dict[str, ModelSchemaDeclaration] = field(default_factory=dict)
    declaration_resolver: DeclarationScopeResolver | None = None

    @property
    def declaration_expansion(self) -> DeclarationExpansionContext:
        """Build the public declaration expansion context for non-model resources."""

        return DeclarationExpansionContext(
            declarations=DeclarationResolutionContext(
                enums=self.public_enums,
                constants=self.public_constants,
            ),
            value_renderer=self.value_renderer,
            collection_rendering=self.collection_rendering,
            resolver=self.declaration_resolver,
        )


@dataclass(frozen=True)
class ModelInputScopeBuild:
    """Model inputs paired with public declaration artifacts and updated context."""

    inputs: tuple[CompileModelInput, ...]
    declarations: DeclarationResolutionContext
    context: ModelInputBuildContext
    diagnostics: tuple[CompilerDiagnostic, ...] = ()


@dataclass(frozen=True)
class CompileSqlReference:
    """One logical SQL reference discovered from compiled SQL text."""

    ref_kind: SqlReferenceKind | str
    ref_name: str
    ref_package: str | None = None
    call_argument_count: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref_kind", SqlReferenceKind(self.ref_kind))


@dataclass(frozen=True)
class CompiledLineageSourceFact:
    """Compact upstream column fact extracted during SQL analysis."""

    resource_type: CompiledResourceType | str
    resource_name: str
    column_name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource_type", CompiledResourceType(self.resource_type))


@dataclass(frozen=True)
class CompiledLineageColumnFact:
    """Compact output column lineage fact extracted during SQL analysis."""

    output_column: str
    upstream_columns: tuple[CompiledLineageSourceFact, ...] = field(default_factory=tuple)
    transform_kind: ColumnTransformKind = ColumnTransformKind.UNKNOWN
    confidence: ColumnLineageConfidence = ColumnLineageConfidence.UNKNOWN


@dataclass(frozen=True)
class PolyglotAnalysisResult:
    """Outcome of one Polyglot column and lineage analysis pass."""

    analysis_succeeded: bool
    columns: tuple[InferredColumn, ...] | None = None
    lineage_columns: tuple[CompiledLineageColumnFact, ...] = field(default_factory=tuple)
    has_star: bool = False


@dataclass(frozen=True)
class AnalysisCacheContext:
    """Shared project-local analysis cache identity for one compile invocation."""

    root: Path
    shared_fingerprint: str
    signature_namespace: str = "default"


@dataclass(frozen=True)
class CompileAnalysisSelection:
    """Selection inputs used to limit deep model SQL analysis."""

    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    auto_load_sources: bool = False
    no_cache: bool = False


@dataclass(frozen=True)
class CompiledObjectKey:
    """Stable logical identity for one compiled resource or external dependency."""

    resource_type: CompiledResourceType | str
    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource_type", CompiledResourceType(self.resource_type))


@dataclass(frozen=True)
class CompileSqlScenarioCte:
    """One top-level SQL-native scenario CTE extracted after macro expansion."""

    name: str
    sql_body: str


@dataclass(frozen=True)
class CompileSqlScenarioCtes:
    """Extracted top-level SQL-native scenario CTE semantics."""

    authored_ctes: tuple[CompileSqlScenarioCte, ...] = field(default_factory=tuple)
    expected_ctes: tuple[CompileSqlScenarioCte, ...] = field(default_factory=tuple)
    assertion_ctes: tuple[CompileSqlScenarioCte, ...] = field(default_factory=tuple)
    source_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    ref_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    seed_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    dbt_ref_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    expected_model_names: tuple[str, ...] = field(default_factory=tuple)
    assertion_names: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FunctionArgument:
    """One SQL function argument with an adapter-native type string."""

    name: str
    type: str


@dataclass(frozen=True)
class FunctionReturnColumn:
    """One named table-function return column with an adapter-native type string."""

    name: str
    type: str


@dataclass(frozen=True)
class CompileSqlFunctionInput:
    """One discovered SQL function with validated compile-time metadata."""

    function_file: DiscoveredSqlFunctionFile | DiscoveredPythonFunctionFile
    name: str
    arguments: tuple[FunctionArgument, ...]
    returns: str
    body_sql: str
    return_columns: tuple[FunctionReturnColumn, ...] = field(default_factory=tuple)
    references: tuple[CompileSqlReference, ...] = field(default_factory=tuple)
    database: str | None = None
    schema: str | None = None
    logical_database: str | None = None
    logical_schema: str | None = None
    fingerprint_database: str | None = None
    fingerprint_schema: str | None = None
    fingerprint_logical_database: str | None = None
    fingerprint_logical_schema: str | None = None
    language: FunctionLanguage = FunctionLanguage.SQL
    runtime_version: str | None = None
    entry_point: str | None = None
    packages: tuple[str, ...] = field(default_factory=tuple)
    replay_on_change: str | None = None
    declaration_usages: tuple[UsageRecord, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompileModelInput:
    """One discovered model file with its attached schema metadata, if any."""

    model_file: DiscoveredSqlModelFile
    config: CompileModelConfig = field(default_factory=CompileModelConfig)
    query_sql: str = ""
    macro_source_sql: str = ""
    references: tuple[CompileSqlReference, ...] = field(default_factory=tuple)
    schema_entry: SchemaModelEntry | None = None
    schema_file: DiscoveredSchemaFile | None = None
    sql_validation_enabled: bool = False
    enum_declarations: tuple[EnumDeclaration, ...] = field(default_factory=tuple)
    constant_declarations: tuple[ConstantDeclaration, ...] = field(default_factory=tuple)
    enum_columns: dict[str, EnumDeclaration] = field(default_factory=dict)
    macro_deps: tuple[str, ...] = field(default_factory=tuple)
    macro_usages: tuple[UsageRecord, ...] = field(default_factory=tuple)
    declaration_usages: tuple[UsageRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompileSeedInput:
    """One discovered seed file with its attached seed metadata."""

    seed_file: DiscoveredSeedFile
    schema_entry: SchemaSeedEntry
    schema_file: DiscoveredSchemaFile


@dataclass(frozen=True)
class CompileSourceInput:
    """One normalized source declaration with its source file provenance."""

    source_entry: SourceEntry
    source_file: DiscoveredSourceFile
    declaration_usages: tuple[UsageRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompileSqlScenarioInput:
    """One discovered SQL-native scenario with compile-time SQL expansion applied."""

    scenario_file: DiscoveredSqlScenarioFile
    sql_body: str
    authored_ctes: tuple[CompileSqlScenarioCte, ...] = field(default_factory=tuple)
    expected_ctes: tuple[CompileSqlScenarioCte, ...] = field(default_factory=tuple)
    assertion_ctes: tuple[CompileSqlScenarioCte, ...] = field(default_factory=tuple)
    source_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    ref_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    seed_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    dbt_ref_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    expected_model_names: tuple[str, ...] = field(default_factory=tuple)
    assertion_names: tuple[str, ...] = field(default_factory=tuple)
    assertion_target_model_names: tuple[str, ...] = field(default_factory=tuple)
    target_model_names: tuple[str, ...] = field(default_factory=tuple)
    declaration_usages: tuple[UsageRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompileAuditInput:
    """One discovered SQL audit block with compile-time SQL expansion applied."""

    audit_file: DiscoveredAuditFile
    audit_block: DiscoveredAuditBlock
    sql_body: str
    evaluation_mode: AuditEvaluationMode = AuditEvaluationMode.VIOLATIONS
    measurement_contract: MeasurementContract | None = None
    thresholds: MeasurementThresholds | None = None
    minimum_samples: int | None = None
    measure_sql: str | None = None
    evidence_sql: str | None = None
    evidence_limit: int | None = None
    references: tuple[CompileSqlReference, ...] = field(default_factory=tuple)
    attached_target_kind: AttachedAuditTargetKind | str | None = None
    attached_target_name: str | None = None
    attached_column_name: str | None = None
    severity: AuditSeverity | None = None
    run_scope: str | None = None
    always_run: bool = False
    declaration_usages: tuple[UsageRecord, ...] = field(default_factory=tuple)
    name: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        if self.attached_target_kind is not None:
            object.__setattr__(
                self,
                "attached_target_kind",
                AttachedAuditTargetKind(self.attached_target_kind),
            )


@dataclass(frozen=True)
class CompileProjectInputs:
    """Attached project view used as the first pre-semantic compile input snapshot."""

    project_config: ProjectConfig
    local_config: LocalConfig
    discovered_inputs: DiscoveredProjectInputs
    run_id: str = ""
    effective_target_name: str | None = None
    effective_target: TargetConfig | None = None
    compile_cache_dir: Path | None = None
    effective_connection: dict[str, object] = field(default_factory=dict)
    effective_settings: SettingsConfig = field(default_factory=SettingsConfig)
    effective_vars: dict[str, object] = field(default_factory=dict)
    loaded_macros: dict[str, LoadedMacro] = field(default_factory=dict)
    public_enums: dict[str, EnumDeclaration] = field(default_factory=dict)
    public_constants: dict[str, ConstantDeclaration] = field(default_factory=dict)
    model_inputs: tuple[CompileModelInput, ...] = field(default_factory=tuple)
    seed_inputs: tuple[CompileSeedInput, ...] = field(default_factory=tuple)
    source_inputs: tuple[CompileSourceInput, ...] = field(default_factory=tuple)
    sql_function_inputs: tuple[CompileSqlFunctionInput, ...] = field(default_factory=tuple)
    test_inputs: tuple[CompileSqlTestInput, ...] = field(default_factory=tuple)
    scenario_inputs: tuple[CompileSqlScenarioInput, ...] = field(default_factory=tuple)
    audit_inputs: tuple[CompileAuditInput, ...] = field(default_factory=tuple)
    diagnostics: tuple[CompilerDiagnostic, ...] = field(default_factory=tuple)
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None
    scope_index: ScopeIndex = field(default_factory=ScopeIndex)


@dataclass(frozen=True)
class CompiledRelationLocation:
    """Logical and physical relation location resolved during compile."""

    database: str | None
    schema: str | None
    name: str
    qualified_name: str | None
    logical_schema: str | None = None
    logical_database: str | None = None


@dataclass(frozen=True)
class CompiledModel:
    """Planner-ready compiled model metadata."""

    key: CompiledObjectKey
    deps: tuple[CompiledObjectKey, ...]
    name: str
    relative_path: Path
    query_sql: str
    config: CompileModelConfig
    destination: CompiledRelationLocation
    references: tuple[CompileSqlReference, ...] = field(default_factory=tuple)
    schema_entry: SchemaModelEntry | None = None
    inferred_columns: tuple[InferredColumn, ...] | None = None
    fast_lineage_columns: tuple[CompiledLineageColumnFact, ...] | None = None
    fast_lineage_has_star: bool = False
    authored_sql: str = ""
    output_column_locations: dict[str, SourceLocation] = field(default_factory=dict)
    macro_deps: tuple[str, ...] = field(default_factory=tuple)
    enum_declarations: tuple[EnumDeclaration, ...] = field(default_factory=tuple)
    constant_declarations: tuple[ConstantDeclaration, ...] = field(default_factory=tuple)
    enum_columns: dict[str, EnumDeclaration] = field(default_factory=dict)


@dataclass(frozen=True)
class CompiledSource:
    """Planner-ready compiled source metadata."""

    key: CompiledObjectKey
    deps: tuple[CompiledObjectKey, ...]
    name: str
    source_entry: SourceEntry
    source_file: DiscoveredSourceFile


@dataclass(frozen=True)
class CompiledSeed:
    """Planner-ready compiled seed metadata."""

    key: CompiledObjectKey
    deps: tuple[CompiledObjectKey, ...]
    name: str
    seed_file: DiscoveredSeedFile
    schema_entry: SchemaSeedEntry
    schema_file: DiscoveredSchemaFile
    destination: CompiledRelationLocation
    external: bool = False


@dataclass(frozen=True)
class CompiledFunction:
    """Planner-ready compiled SQL function metadata."""

    key: CompiledObjectKey
    deps: tuple[CompiledObjectKey, ...]
    name: str
    relative_path: Path
    arguments: tuple[FunctionArgument, ...]
    returns: str
    body_sql: str
    destination: CompiledRelationLocation
    fingerprint_destination: CompiledRelationLocation
    return_columns: tuple[FunctionReturnColumn, ...] = field(default_factory=tuple)
    references: tuple[CompileSqlReference, ...] = field(default_factory=tuple)
    language: FunctionLanguage = FunctionLanguage.SQL
    source_file_path: Path | None = None
    runtime_version: str | None = None
    entry_point: str | None = None
    packages: tuple[str, ...] = field(default_factory=tuple)
    replay_on_change: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompiledAudit:
    """Compiled audit metadata selected by scope dependencies."""

    key: CompiledObjectKey
    scope_deps: tuple[CompiledObjectKey, ...]
    name: str
    definition_name: str
    audit_file: DiscoveredAuditFile
    audit_block: DiscoveredAuditBlock
    sql_body: str
    evaluation_mode: AuditEvaluationMode = AuditEvaluationMode.VIOLATIONS
    measurement_contract: MeasurementContract | None = None
    thresholds: MeasurementThresholds | None = None
    minimum_samples: int | None = None
    measure_sql: str | None = None
    evidence_sql: str | None = None
    evidence_limit: int | None = None
    references: tuple[CompileSqlReference, ...] = field(default_factory=tuple)
    attached_target_kind: AttachedAuditTargetKind | None = None
    attached_target_name: str | None = None
    attached_column_name: str | None = None
    severity: AuditSeverity | None = None
    run_scope: str | None = None
    always_run: bool = False
    description: str | None = None


@dataclass(frozen=True)
class CompiledSqlScenario:
    """Compiled SQL-native scenario metadata selected by inferred graph targets."""

    key: CompiledObjectKey
    name: str
    scenario_file: DiscoveredSqlScenarioFile
    sql_body: str
    authored_ctes: tuple[CompileSqlScenarioCte, ...] = field(default_factory=tuple)
    expected_ctes: tuple[CompileSqlScenarioCte, ...] = field(default_factory=tuple)
    assertion_ctes: tuple[CompileSqlScenarioCte, ...] = field(default_factory=tuple)
    source_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    ref_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    seed_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    dbt_ref_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    expected_model_names: tuple[str, ...] = field(default_factory=tuple)
    assertion_names: tuple[str, ...] = field(default_factory=tuple)
    assertion_target_model_names: tuple[str, ...] = field(default_factory=tuple)
    target_model_names: tuple[str, ...] = field(default_factory=tuple)
    source_path: Path | None = None
    ownership_root: Path | None = None

    def __post_init__(self) -> None:
        if self.source_path is None:
            object.__setattr__(self, "source_path", self.scenario_file.relative_path)
        if self.ownership_root is None:
            object.__setattr__(self, "ownership_root", self.scenario_file.ownership_root)
        if not self.target_model_names:
            object.__setattr__(
                self,
                "target_model_names",
                tuple(
                    dict.fromkeys((*self.expected_model_names, *self.assertion_target_model_names))
                ),
            )


@dataclass(frozen=True)
class CompiledProject:
    """Planner-ready whole-project compile output."""

    run_id: str
    effective_target_name: str | None
    effective_connection: dict[str, object]
    effective_vars: dict[str, object]
    effective_target_database: str | None = None
    effective_target_schema: str | None = None
    compile_cache_dir: Path | None = None
    settings: SettingsConfig = field(default_factory=SettingsConfig)
    scenario: ScenarioConfig = field(default_factory=ScenarioConfig)
    models: tuple[CompiledModel, ...] = field(default_factory=tuple)
    sources: tuple[CompiledSource, ...] = field(default_factory=tuple)
    seeds: tuple[CompiledSeed, ...] = field(default_factory=tuple)
    functions: tuple[CompiledFunction, ...] = field(default_factory=tuple)
    audits: tuple[CompiledAudit, ...] = field(default_factory=tuple)
    sql_tests: tuple[CompiledSqlTest, ...] = field(default_factory=tuple)
    sql_scenarios: tuple[CompiledSqlScenario, ...] = field(default_factory=tuple)
    loader_functions: tuple[DiscoveredLoaderFunction, ...] = field(default_factory=tuple)
    hook_functions: tuple[DiscoveredHookFunction, ...] = field(default_factory=tuple)
    sql_hook_files: tuple[DiscoveredSqlHookFile, ...] = field(default_factory=tuple)
    materialization_files: tuple[DiscoveredMaterializationFile, ...] = field(default_factory=tuple)
    public_enums: dict[str, EnumDeclaration] = field(default_factory=dict)
    public_constants: dict[str, ConstantDeclaration] = field(default_factory=dict)
    loaded_macros: dict[str, LoadedMacro] = field(default_factory=dict)
    diagnostics: tuple[CompilerDiagnostic, ...] = field(default_factory=tuple)
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None
    scope_index: ScopeIndex = field(default_factory=ScopeIndex)


@dataclass(frozen=True)
class CompileSqlTestCte:
    """One top-level SQL-native test CTE extracted after macro expansion."""

    name: str
    sql_body: str


@dataclass(frozen=True)
class CompileModelSqlTestCtes:
    """Extracted model-mode SQL-native test CTE semantics."""

    authored_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
    macro_mocks: dict[str, str] = field(default_factory=dict)
    mock_model_names: tuple[str, ...] = field(default_factory=tuple)
    mock_source_names: tuple[str, ...] = field(default_factory=tuple)
    mock_seed_names: tuple[str, ...] = field(default_factory=tuple)
    mock_dbt_ref_names: tuple[str, ...] = field(default_factory=tuple)
    expected_model_names: tuple[str, ...] = field(default_factory=tuple)
    assertion_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
    assertion_names: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompileDirectLogicSqlTestCtes:
    """Extracted direct-logic SQL-native test CTE semantics."""

    mode: SqlTestMode
    helper_ctes: tuple[CompileSqlTestCte, ...]
    actual_cte: CompileSqlTestCte
    expected_cte: CompileSqlTestCte


@dataclass(frozen=True)
class CompileSqlTestCtes:
    """Extracted top-level SQL-native test CTE semantics."""

    mode: SqlTestMode
    payload: CompileModelSqlTestCtes | CompileDirectLogicSqlTestCtes


@dataclass(frozen=True)
class CompileModelSqlTestInputPayload:
    """Model-mode SQL test compile payload."""

    authored_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
    macro_mocks: dict[str, str] = field(default_factory=dict)
    mock_model_names: tuple[str, ...] = field(default_factory=tuple)
    mock_source_names: tuple[str, ...] = field(default_factory=tuple)
    mock_seed_names: tuple[str, ...] = field(default_factory=tuple)
    mock_dbt_ref_names: tuple[str, ...] = field(default_factory=tuple)
    expected_model_names: tuple[str, ...] = field(default_factory=tuple)
    assertion_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
    assertion_names: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompileDirectLogicSqlTestInputPayload:
    """Direct-logic SQL test compile payload."""

    actual_cte: CompileSqlTestCte
    expected_cte: CompileSqlTestCte
    mode: SqlTestMode
    helper_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
    tested_resource_names: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompileSqlTestInput:
    """One discovered SQL-native test block with compile-time SQL expansion applied."""

    test_file: DiscoveredSqlTestFile
    test_block: DiscoveredSqlTestBlock
    sql_body: str
    mode: SqlTestMode = DEFAULT_SQL_TEST_MODE
    payload: CompileModelSqlTestInputPayload | CompileDirectLogicSqlTestInputPayload = field(
        default_factory=CompileModelSqlTestInputPayload
    )
    declaration_usages: tuple[UsageRecord, ...] = field(default_factory=tuple)
    parent_name: str | None = None
    case_name: str | None = None
    case_index: int | None = None
    parameter_schema: tuple[SqlTestParameterDeclaration, ...] = field(default_factory=tuple)
    parameter_values: tuple[tuple[str, SqlValue], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompiledModelSqlTestPayload:
    """Compiled model-mode SQL test payload."""

    authored_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
    macro_mocks: dict[str, str] = field(default_factory=dict)
    model_query_overrides: dict[str, str] = field(default_factory=dict)
    mock_model_names: tuple[str, ...] = field(default_factory=tuple)
    mock_source_names: tuple[str, ...] = field(default_factory=tuple)
    mock_seed_names: tuple[str, ...] = field(default_factory=tuple)
    mock_dbt_ref_names: tuple[str, ...] = field(default_factory=tuple)
    expected_model_names: tuple[str, ...] = field(default_factory=tuple)
    assertion_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
    assertion_names: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SqlExpansionContext:
    """Everything needed to expand one project's authored SQL bodies."""

    effective_vars: dict[str, object]
    loaded_macros: dict[str, LoadedMacro]
    macro_context: MacroContext
    enums: dict[str, EnumDeclaration]
    constants: dict[str, ConstantDeclaration]
    value_renderer: TypedSqlValueRenderer
    collection_rendering: CollectionRendering
    local_declarations: dict[Path, DeclarationResolutionContext] = field(default_factory=dict)
    declaration_resolver: DeclarationScopeResolver | None = None


@dataclass(frozen=True)
class ExpansionSpan:
    """One substituted region, pairing its source range with its rendered range."""

    source_start: int
    source_end: int
    output_start: int
    output_end: int


@dataclass(frozen=True)
class MappedOffset:
    """An offset in rendered SQL resolved back onto the text that produced it."""

    offset: int
    generated: bool


@dataclass(frozen=True)
class CompiledDirectLogicSqlTestPayload:
    """Compiled direct-logic SQL test payload."""

    actual_cte: CompileSqlTestCte
    expected_cte: CompileSqlTestCte
    mode: SqlTestMode = DEFAULT_SQL_TEST_MODE
    helper_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
    tested_resource_names: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompiledSqlTestResource:
    """One direct SQL test resource with its authored resource kind."""

    kind: SqlTestMode
    name: str


@dataclass(frozen=True)
class CompiledSqlTest:
    """Compiled SQL-native unit test metadata selected by expected targets."""

    key: CompiledObjectKey
    scope_deps: tuple[CompiledObjectKey, ...]
    name: str
    test_file: DiscoveredSqlTestFile
    test_block: DiscoveredSqlTestBlock
    sql_body: str
    mode: SqlTestMode = DEFAULT_SQL_TEST_MODE
    payload: CompiledModelSqlTestPayload | CompiledDirectLogicSqlTestPayload = field(
        default_factory=CompiledModelSqlTestPayload
    )
    source_path: Path | None = None
    ownership_root: Path | None = None
    block_index: int | None = None
    explicit_name: str | None = None
    parent_name: str | None = None
    case_name: str | None = None
    case_index: int | None = None
    case_fingerprint: str | None = None
    parameter_schema: tuple[SqlTestParameterDeclaration, ...] = field(default_factory=tuple)
    parameter_values: tuple[tuple[str, SqlValue], ...] = field(default_factory=tuple)
    expected_model_names: tuple[str, ...] = field(default_factory=tuple)
    assertion_names: tuple[str, ...] = field(default_factory=tuple)
    assertion_target_model_names: tuple[str, ...] = field(default_factory=tuple)
    target_model_names: tuple[str, ...] = field(default_factory=tuple)
    tested_resources: tuple[CompiledSqlTestResource, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.source_path is None:
            object.__setattr__(self, "source_path", self.test_file.relative_path)
        if self.ownership_root is None:
            object.__setattr__(self, "ownership_root", self.test_file.ownership_root)
        if self.block_index is None:
            object.__setattr__(self, "block_index", self.test_block.test_index)
        if self.explicit_name is None and self.test_block.name is not None:
            object.__setattr__(self, "explicit_name", self.test_block.name)
        if self.parent_name is None:
            object.__setattr__(
                self,
                "parent_name",
                self.test_block.name or self.test_file.relative_path.stem,
            )
