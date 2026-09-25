"""Structured runtime models for project compilation."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, overload

from sqlbuild.compiler.auditing.models import MeasurementContract, MeasurementThresholds
from sqlbuild.compiler.auditing.types import AuditEvaluationMode, AuditSeverity
from sqlbuild.compiler.compile.constants import DEFAULT_SQL_TEST_MODE
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
    CompactBatchResponseCallback,
    CompiledResourceType,
    CompileInputsReadyCallback,
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
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic
from sqlbuild.spec.contracts.models import (
    DefaultsConfig,
    LocalConfig,
    MaterializationDefaultsConfig,
    ProjectConfig,
    ResolvedTableType,
    ResolvedTimeTravelRetention,
    ScenarioConfig,
    SchemaColumn,
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
class FixtureColumnInference:
    """Inferred fixture columns plus outputs that are explicitly bare NULL literals."""

    columns: tuple[InferredColumn, ...]
    null_literal_names: frozenset[str]
    quoted_names: frozenset[str]


@dataclass(frozen=True)
class DynamicColumnFamilyProof:
    """Compiler evidence for one declared runtime-generated column family."""

    name: str
    inferred_type: str | None = None


@dataclass(frozen=True)
class DynamicColumnContractProof:
    """Closed output-shape evidence for a dynamic column contract."""

    output_proven: bool
    fixed_columns: tuple[InferredColumn, ...] = field(default_factory=tuple)
    families: tuple[DynamicColumnFamilyProof, ...] = field(default_factory=tuple)
    input_relations: tuple[str, ...] = field(default_factory=tuple)
    failure_reason: str | None = None
    bare_dynamic_pivot: bool = False


@dataclass(frozen=True)
class CteFactResolvers:
    """Expression resolvers used for conservative CTE fact recovery."""

    expression_type: Callable[..., Any]
    nullability: Callable[..., Any]
    shallow_nullability: Callable[..., Any]
    alias_nullability: Callable[..., Any]


@dataclass(frozen=True)
class NonNullFilterContext:
    """Resolved relations and columns constrained by non-null filters."""

    relations: tuple[tuple[str, dict[str, InferredNullability]], ...]
    columns: frozenset[tuple[str, str]]


@dataclass(frozen=True)
class CompileModelConfig:
    """Pre-semantic effective config layers attached to a model input."""

    values: dict[str, object] = field(default_factory=dict)
    model_header_keys: tuple[str, ...] = field(default_factory=tuple)
    matched_path_default: str | None = None
    logical_schema: str | None = None
    layer_schema: str | None = None
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
    resource_specific: frozenset[ResourceIdentity] | None = None
    contexts_by_directory: dict[tuple[str, str], DeclarationResolutionContext] = field(
        default_factory=dict, compare=False, repr=False
    )

    def cache_context(self, *, key: tuple[str, str], context: DeclarationResolutionContext) -> None:
        """Retain a process-local context for equivalent lexical consumers."""
        self.contexts_by_directory[key] = context


@dataclass(frozen=True)
class DeclarationScopeBuild:
    """Static artifact and process-local values shared by compile attachment phases."""

    loaded_macros: dict[str, LoadedMacro]
    index: ScopeIndex
    resolver: DeclarationScopeResolver


@dataclass(frozen=True)
class MacroContext:
    """Expose target settings and caller-visible declarations to a Python SQL macro."""

    adapter_name: str
    sql_analysis_enabled: bool
    target_name: str | None
    vars: dict[str, object] = field(default_factory=dict)
    constants: Mapping[str, object] = field(default_factory=dict)
    enums: Mapping[str, Mapping[str, str | int]] = field(default_factory=dict)
    _value_renderer: TypedSqlValueRenderer | None = field(default=None, repr=False, compare=False)
    _collection_rendering: CollectionRendering = field(
        default=CollectionRendering.VALUE_LIST, repr=False, compare=False
    )
    _constant_declarations: Mapping[str, ConstantDeclaration] = field(
        default_factory=dict, repr=False, compare=False
    )

    def render_constant(self, name: str) -> str:
        """Render one visible constant as an adapter-safe SQL value."""

        if self._value_renderer is None:
            raise CompileInputError(
                "Constant SQL rendering is available only during a project macro invocation"
            )
        _ = self.constants[name]
        declaration: ConstantDeclaration | None = self._constant_declarations.get(name)
        if declaration is None:
            raise CompileInputError(
                "Constant SQL rendering requires a declaration resolved for this macro invocation"
            )
        from sqlbuild.compiler.compile._helpers.render.declarations import (
            render_constant_declaration,
        )

        return render_constant_declaration(
            declaration=declaration,
            value_renderer=self._value_renderer,
            collection_rendering=self._collection_rendering,
        )

    def render_enum_member(self, *, enum_name: str, member_name: str) -> str:
        """Render one visible enum member as a SQL scalar literal."""

        value: str | int = self.enums[enum_name][member_name]
        from sqlbuild.compiler.compile._helpers.render.declarations import (
            render_enum_member_value,
        )

        return render_enum_member_value(value=value)


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
    macro_visibility: dict[str, tuple[VisibilityRecord, ...]] = field(default_factory=dict)
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


@dataclass(frozen=True, eq=False)
class CompactLineageFacts(Sequence[CompiledLineageColumnFact]):
    """Indexed native lineage rows with lazy object projection."""

    string_pool: tuple[str, ...]
    rows: tuple[
        tuple[int, int, int, tuple[tuple[int, int, int], ...]],
        ...,
    ]
    resource_name_indexes: dict[int, int] = field(default_factory=dict)
    _cache: dict[int, CompiledLineageColumnFact] = field(
        default_factory=dict,
        init=False,
        repr=False,
        compare=False,
    )

    def __len__(self) -> int:
        return len(self.rows)

    @overload
    def __getitem__(self, index: int) -> CompiledLineageColumnFact: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[CompiledLineageColumnFact]: ...

    def __getitem__(
        self, index: int | slice
    ) -> CompiledLineageColumnFact | Sequence[CompiledLineageColumnFact]:
        if isinstance(index, slice):
            return tuple(self[item_index] for item_index in range(*index.indices(len(self))))
        normalized_index: int = index if index >= 0 else len(self) + index
        if normalized_index < 0 or normalized_index >= len(self):
            raise IndexError(index)
        cached: CompiledLineageColumnFact | None = self._cache.get(normalized_index)
        if cached is not None:
            return cached
        name_index, transform_code, confidence_code, sources = self.rows[normalized_index]
        fact: CompiledLineageColumnFact = CompiledLineageColumnFact(
            output_column=self.string_pool[name_index],
            upstream_columns=tuple(
                CompiledLineageSourceFact(
                    resource_type=self.string_pool[source[0]],
                    resource_name=self.resource_name(source[1]),
                    column_name=self.string_pool[source[2]],
                )
                for source in sources
            ),
            transform_kind=self.transform_kind(transform_code),
            confidence=self.confidence(confidence_code),
        )
        self._cache[normalized_index] = fact
        return fact

    def __iter__(self) -> Iterator[CompiledLineageColumnFact]:
        return (self[index] for index in range(len(self)))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Sequence):
            return NotImplemented
        return tuple(self) == tuple(other)

    def resource_name(self, index: int) -> str:
        """Resolve a canonical native relation index to this model's resource name."""

        return self.string_pool[self.resource_name_indexes.get(index, index)]

    @staticmethod
    def transform_kind(code: int) -> ColumnTransformKind:
        return (
            ColumnTransformKind.DIRECT,
            ColumnTransformKind.CAST,
            ColumnTransformKind.EXPRESSION,
            ColumnTransformKind.AGGREGATION,
            ColumnTransformKind.STAR,
            ColumnTransformKind.CONSTANT,
        )[code]

    @staticmethod
    def confidence(code: int) -> ColumnLineageConfidence:
        return (
            ColumnLineageConfidence.UNKNOWN,
            ColumnLineageConfidence.HIGH,
            ColumnLineageConfidence.MEDIUM,
        )[code]


@dataclass(frozen=True)
class PolyglotAnalysisResult:
    """Outcome of one Polyglot column and lineage analysis pass."""

    analysis_succeeded: bool
    columns: tuple[InferredColumn, ...] | None = None
    lineage_columns: Sequence[CompiledLineageColumnFact] = field(default_factory=tuple)
    has_star: bool = False
    binding_diagnostics: tuple[SqlBindingDiagnostic, ...] = field(default_factory=tuple)
    binding_validated: bool = False


@dataclass(frozen=True)
class AnalysisCacheContext:
    """Shared project-local analysis cache identity for one compile invocation."""

    root: Path
    shared_fingerprint: str
    signature_namespace: str = "default"


@dataclass(frozen=True)
class CompileAnalysisSelection:
    """Deep-analysis selection and invocation-local preparation observer."""

    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    auto_load_sources: bool = False
    no_cache: bool = False
    on_inputs_ready: CompileInputsReadyCallback | None = field(
        default=None, compare=False, repr=False
    )


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
    sql_expansion: CompiledSqlExpansion | None = field(default=None, compare=False, repr=False)


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
    macro_context: MacroContext | None = field(default=None, repr=False, compare=False)
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
    declaration_scope: DeclarationScopeBuild | None = field(default=None, repr=False, compare=False)


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
    fast_lineage_columns: Sequence[CompiledLineageColumnFact] | None = None
    fast_lineage_has_star: bool = False
    authored_sql: str = ""
    authored_query_sql: str = ""
    output_column_locations: dict[str, SourceLocation] = field(default_factory=dict)
    extract_implicit_alias_columns: bool = True
    macro_deps: tuple[str, ...] = field(default_factory=tuple)
    enum_declarations: tuple[EnumDeclaration, ...] = field(default_factory=tuple)
    constant_declarations: tuple[ConstantDeclaration, ...] = field(default_factory=tuple)
    enum_columns: dict[str, EnumDeclaration] = field(default_factory=dict)
    binding_diagnostics: tuple[CompilerDiagnostic, ...] = field(default_factory=tuple)
    binding_validated: bool = False
    dynamic_column_contract: DynamicColumnContractProof | None = None


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
    sql_expansions: dict[Path, CompiledSqlExpansion] = field(
        default_factory=dict, compare=False, repr=False
    )


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
    mock_table_function_names: tuple[str, ...] = field(default_factory=tuple)
    expected_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
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
    mock_table_function_names: tuple[str, ...] = field(default_factory=tuple)
    expected_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
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
    mock_table_function_names: tuple[str, ...] = field(default_factory=tuple)
    expected_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
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
class CompiledSqlExpansion:
    """Process-local authored-to-expanded SQL evidence shared with compiler checks."""

    authored_sql: str
    expanded_sql: str
    passes: tuple[tuple[ExpansionSpan, ...], ...]


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


@dataclass(frozen=True)
class CompactProjectedFacts:
    """Decoded compact projection and lineage rows shared by projected analyses."""

    columns: tuple[InferredColumn, ...]
    lineage_rows: tuple[
        tuple[int, int, int, tuple[tuple[int, int, int], ...]],
        ...,
    ]


@dataclass(frozen=True)
class CompactBatchExecutionOptions:
    """Optional binding work and cache publication for one native batch."""

    binding_schemas: tuple[dict[str, dict[str, str]] | None, ...] | None = None
    on_response: CompactBatchResponseCallback | None = None


@dataclass(frozen=True)
class CompactBatchPreparation:
    """Deduplicated native request data and ordered cleaned SQL inputs."""

    cleaned_sql: tuple[str, ...]
    queries: tuple[dict[str, object], ...]
    templates: tuple[dict[str, object], ...]
    projections: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class CompactAnalysisCacheModel:
    """One ordered model identity and its project-model dependencies."""

    name: str
    cache_key: str | None
    upstream_names: tuple[str, ...]


@dataclass(frozen=True)
class CompactAnalysisCachePlan:
    """Current invocation identity for one compact analysis generation."""

    context: AnalysisCacheContext
    batch_key: str
    cache_keys: tuple[str, ...]
    reuse_keys: tuple[str, ...]


@dataclass(frozen=True)
class CompactAnalysisCacheCandidate:
    """Validated persisted generation and positions safe for reuse."""

    matching_indexes: tuple[int, ...]
    preparation: CompactBatchPreparation
    response: object


@dataclass(frozen=True)
class CompactProjectionCaches:
    """Shared identity caches used while decoding compact native facts."""

    columns: dict[tuple[int, int | None, int], InferredColumn] | None = None
    facts: dict[int, CompactProjectedFacts] | None = None
    decoded_facts: (
        dict[
            int,
            tuple[InferredColumn, tuple[int, int, int, tuple[tuple[int, int, int], ...]]],
        ]
        | None
    ) = None

    def column(self, key: tuple[int, int | None, int]) -> InferredColumn | None:
        return self.columns.get(key) if self.columns is not None else None

    def remember_column(self, *, key: tuple[int, int | None, int], column: InferredColumn) -> None:
        if self.columns is not None:
            self.columns[key] = column

    def fact(self, template_index: int | None) -> CompactProjectedFacts | None:
        if self.facts is None or template_index is None:
            return None
        return self.facts.get(template_index)

    def remember_fact(self, *, template_index: int | None, fact: CompactProjectedFacts) -> None:
        if self.facts is not None and template_index is not None:
            self.facts[template_index] = fact

    def decoded_fact(
        self, fact_index: int
    ) -> tuple[InferredColumn, tuple[int, int, int, tuple[tuple[int, int, int], ...]]] | None:
        return self.decoded_facts.get(fact_index) if self.decoded_facts is not None else None

    def remember_decoded_fact(
        self,
        *,
        fact_index: int,
        fact: tuple[InferredColumn, tuple[int, int, int, tuple[tuple[int, int, int], ...]]],
    ) -> None:
        if self.decoded_facts is not None:
            self.decoded_facts[fact_index] = fact


@dataclass(frozen=True)
class ProjectedAnalysisRequest:
    """Inputs needed to project one native analysis into the public result contract."""

    analysis: dict[str, Any] | None
    binding_diagnostics: tuple[SqlBindingDiagnostic, ...]
    binding_validated: bool
    compact_rows: list[object] | None = None
    compact_fact_rows: list[object] | None = None
    string_pool: tuple[str, ...] = ()
    caches: CompactProjectionCaches = field(default_factory=CompactProjectionCaches)
    template_index: int | None = None
    resource_name_indexes: dict[int, int] = field(default_factory=dict)


@dataclass(frozen=True)
class NativeCompactAnalysis:
    """One native compact result prepared for Python contract projection."""

    cleaned_sql: str
    analysis: dict[str, Any] | None
    projected: bool = False
    binding_diagnostics: tuple[SqlBindingDiagnostic, ...] | None = None
    compact_rows: list[object] | None = None
    compact_fact_rows: list[object] | None = None
    string_pool: tuple[str, ...] = ()
    compact_column_cache: dict[tuple[int, int | None, int], InferredColumn] | None = None
    compact_template_index: int | None = None
    compact_fact_cache: dict[int, CompactProjectedFacts] | None = None
    compact_decoded_fact_cache: (
        dict[
            int,
            tuple[InferredColumn, tuple[int, int, int, tuple[tuple[int, int, int], ...]]],
        ]
        | None
    ) = None
    resource_name_indexes: dict[int, int] = field(default_factory=dict)


@dataclass(frozen=True)
class IdentityPresenceCache:
    """Identity-safe memoization for recursive authored configuration scans."""

    _values: dict[int, tuple[object, bool]] = field(default_factory=dict)

    def get(self, value: object) -> bool | None:
        cached: tuple[object, bool] | None = self._values.get(id(value))
        if cached is None or cached[0] is not value:
            return None
        return cached[1]

    def put(self, *, value: object, result: bool) -> None:
        self._values[id(value)] = (value, result)


@dataclass(frozen=True)
class ModelConfigScanCache:
    """Memoized recursive scans reused while attaching model configuration."""

    template_presence: IdentityPresenceCache = field(default_factory=IdentityPresenceCache)
    macro_presence: IdentityPresenceCache = field(default_factory=IdentityPresenceCache)


@dataclass(frozen=True)
class ModelConfigBuildRequest:
    """Cohesive inputs for one effective model-configuration build."""

    defaults: DefaultsConfig
    path_defaults: dict[str, dict[str, object]]
    matched_path_default: str | None
    model_header_values: dict[str, object]
    effective_vars: dict[str, object]
    target_config: TargetConfig | None
    model_name: str
    effective_target_name: str | None
    run_id: str
    materialization_defaults: MaterializationDefaultsConfig | None = None
    scan_cache: ModelConfigScanCache | None = None


@dataclass(frozen=True)
class CachedModelHeaderColumns:
    """Cached authored MODEL-header columns and source locations."""

    raw_columns: object
    columns: tuple[SchemaColumn, ...]
    column_locations: dict[str, SourceLocation]


@dataclass(frozen=True)
class ModelHeaderColumnCache:
    """Identity-safe cache of parsed authored MODEL-header columns."""

    _values: dict[int, CachedModelHeaderColumns] = field(default_factory=dict)

    def get(self, raw_columns: object) -> CachedModelHeaderColumns | None:
        cached: CachedModelHeaderColumns | None = self._values.get(id(raw_columns))
        if cached is None or cached.raw_columns is not raw_columns:
            return None
        return cached

    def put(self, cached: CachedModelHeaderColumns) -> None:
        self._values[id(cached.raw_columns)] = cached
