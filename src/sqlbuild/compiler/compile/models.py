"""Structured runtime models for project compilation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.compiler.compile.constants import DEFAULT_SQL_TEST_MODE
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
    FunctionLanguage,
    SqlTestMode,
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
)
from sqlbuild.compiler.lineage.types import (
    ColumnLineageConfidence,
    ColumnTransformKind,
    InferredNullability,
)
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver, SqlReferenceKind
from sqlbuild.spec.contracts.models import (
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


@dataclass(frozen=True)
class LoadedMacro:
    """One loaded project macro available for compile-time SQL expansion."""

    name: str
    file_path: Path
    relative_path: Path
    raw_source: str
    function: Callable[..., object]


@dataclass(frozen=True)
class MacroContext:
    """Compile-time context passed to adapter-aware SQL macros."""

    adapter_name: str
    sql_analysis_enabled: bool
    target_name: str | None
    vars: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DeclarationResolutionContext:
    """Project-global declarations available during authored SQL expansion."""

    enums: dict[str, EnumDeclaration] = field(default_factory=dict)
    constants: dict[str, ConstantDeclaration] = field(default_factory=dict)


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
    public_enums: dict[str, EnumDeclaration] = field(default_factory=dict)
    public_constants: dict[str, ConstantDeclaration] = field(default_factory=dict)
    public_model_schemas: dict[str, ModelSchemaDeclaration] = field(default_factory=dict)


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
    fingerprint_database: str | None = None
    fingerprint_schema: str | None = None
    language: FunctionLanguage = FunctionLanguage.SQL
    runtime_version: str | None = None
    entry_point: str | None = None
    packages: tuple[str, ...] = field(default_factory=tuple)
    replay_on_change: str | None = None


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


@dataclass(frozen=True)
class CompileAuditInput:
    """One discovered SQL audit block with compile-time SQL expansion applied."""

    audit_file: DiscoveredAuditFile
    audit_block: DiscoveredAuditBlock
    sql_body: str
    references: tuple[CompileSqlReference, ...] = field(default_factory=tuple)
    attached_target_kind: AttachedAuditTargetKind | str | None = None
    attached_target_name: str | None = None
    attached_column_name: str | None = None
    severity: str | None = None
    run_scope: str | None = None
    always_run: bool = False

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


@dataclass(frozen=True)
class CompiledAudit:
    """Compiled audit metadata selected by scope dependencies."""

    key: CompiledObjectKey
    scope_deps: tuple[CompiledObjectKey, ...]
    name: str
    audit_file: DiscoveredAuditFile
    audit_block: DiscoveredAuditBlock
    sql_body: str
    references: tuple[CompileSqlReference, ...] = field(default_factory=tuple)
    attached_target_kind: AttachedAuditTargetKind | None = None
    attached_target_name: str | None = None
    attached_column_name: str | None = None
    severity: str | None = None
    run_scope: str | None = None
    always_run: bool = False


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


@dataclass(frozen=True)
class CompiledProject:
    """Planner-ready whole-project compile output."""

    run_id: str
    effective_target_name: str | None
    effective_connection: dict[str, object]
    effective_vars: dict[str, object]
    effective_target_database: str | None = None
    effective_target_schema: str | None = None
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
    diagnostics: tuple[CompilerDiagnostic, ...] = field(default_factory=tuple)
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None


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
    local_declarations: dict[Path, DeclarationResolutionContext] = field(default_factory=dict)


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
