"""Structured runtime models for project compilation."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any, overload

import sqlbuild._native as _native
from sqlbuild._native import (
    CollectionRendering,
    ColumnLineageConfidence,
    ColumnTransformKind,
    CompiledDirectLogicSqlTestPayload,
    CompiledLineageColumnFact,
    CompiledModelSqlTestPayload,
    CompiledSqlExpansion,
    CompiledSqlTestResource,
    CompileModelConfig,
    CompileSqlScenarioCte,
    DeclarationExpansionContext,
    DeclarationIdentity,
    DeclarationRecord,
    DeclarationScopeResolver,
    DiagnosticPhase,
    DiagnosticSeverity,
    DiscoveredAuditBlock,
    DiscoveredAuditFile,
    DiscoveredSchemaFile,
    DiscoveredSqlHookFile,
    DiscoveredSqlTestBlock,
    DynamicColumnContractProof,
    LiteralSqlRelation,
    MeasurementContract,
    MeasurementThresholds,
    ModelSchemaDeclaration,
    RelatedLocation,
    ResourceIdentity,
    ScenarioConfig,
    SchemaModelEntry,
    ScopeIndex,
    SettingsConfig,
    SourceLocation,
    SqlLexicalSyntax,
    SqlValue,
    TargetConfig,
    UsageRecord,
    VisibilityRecord,
)
from sqlbuild.compiler.auditing.types import AuditEvaluationMode, AuditSeverity
from sqlbuild.compiler.compile.constants import DEFAULT_SQL_TEST_MODE, MACRO_CONTEXT_PARAMETER_NAME
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
    CompiledAuditView,
    CompiledFunctionView,
    CompiledModelView,
    CompiledResourceType,
    CompiledSeedView,
    CompiledSourceView,
    RelationKeyRow,
    SqlTestMode,
    TypedSqlValueRenderer,
)
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredHookFunction,
    DiscoveredLoaderFunction,
    DiscoveredMaterializationFile,
    DiscoveredSqlModelFile,
    DiscoveredSqlScenarioFile,
    DiscoveredSqlTestFile,
    EnumDeclaration,
    SqlTestParameterDeclaration,
)
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver, SqlReferenceKind


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
    notes: tuple[str, ...] = ()
    affected_rules: tuple[str, ...] = ()

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
class LoadedMacro:
    """One loaded project macro available for compile-time SQL expansion."""

    name: str
    file_path: Path
    relative_path: Path
    raw_source: str
    function: Callable[..., object]
    dependencies: tuple[DeclarationIdentity, ...] = field(default_factory=tuple)

    @cached_property
    def injects_context(self) -> bool:
        """Whether the first positional parameter receives the injected macro context."""

        parameters: tuple[inspect.Parameter, ...] = tuple(
            inspect.signature(self.function).parameters.values()
        )
        return bool(
            parameters
            and parameters[0].kind
            in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
            and parameters[0].name == MACRO_CONTEXT_PARAMETER_NAME
        )


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
    _enforce_explicit_references: bool = field(default=True, repr=False, compare=False)

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
        from sqlbuild._native import render_constant_declaration

        return render_constant_declaration(
            declaration=declaration,
            value_renderer=self._value_renderer,
            collection_rendering=self._collection_rendering,
        )

    def render_enum_member(self, *, enum_name: str, member_name: str) -> str:
        """Render one visible enum member as a SQL scalar literal."""

        value: str | int = self.enums[enum_name][member_name]
        from sqlbuild._native import render_enum_member_value

        return render_enum_member_value(value=value)


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
    sql_lexical_syntax: SqlLexicalSyntax
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


@dataclass(frozen=True, eq=False)
class CompactLineageFacts(Sequence[CompiledLineageColumnFact]):
    """Indexed native lineage rows with lazy object projection."""

    string_pool: tuple[str, ...]
    rows: tuple[
        tuple[int, int, int, tuple[tuple[int, int, int], ...]],
        ...,
    ]
    resource_name_indexes: dict[int, int] = field(default_factory=dict)
    resource_names: dict[int, str] = field(default_factory=dict)
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

        name: str | None = self.resource_names.get(index)
        if name is not None:
            return name
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
class CompiledObjectKey:
    """Stable logical identity for one compiled resource or external dependency."""

    resource_type: CompiledResourceType | str
    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource_type", CompiledResourceType(self.resource_type))


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
    rejected_sql_analysis_opt_out: SourceLocation | None = None
    enum_declarations: tuple[EnumDeclaration, ...] = field(default_factory=tuple)
    constant_declarations: tuple[ConstantDeclaration, ...] = field(default_factory=tuple)
    enum_columns: dict[str, EnumDeclaration] = field(default_factory=dict)
    macro_deps: tuple[str, ...] = field(default_factory=tuple)
    macro_usages: tuple[UsageRecord, ...] = field(default_factory=tuple)
    declaration_usages: tuple[UsageRecord, ...] = field(default_factory=tuple)

    @property
    def reference_rows(self) -> list[tuple[str, str, str | None, int | None]]:
        """Each reference as `(kind, name, package, call argument count)`."""

        return [
            (str(ref.ref_kind), ref.ref_name, ref.ref_package, ref.call_argument_count)
            for ref in self.references
        ]

    @property
    def relation_key_row(self) -> RelationKeyRow:
        """The model's declared key facts, for deriving its unique keys."""

        return _native.relation_key_row(
            "ref", self.model_file.file_path.stem, self.config.values, self.schema_entry
        )

    @property
    def attached_schema_name(self) -> str | None:
        """The name of the schema entry attached to the model, or `None`."""

        return self.schema_entry.name if self.schema_entry is not None else None

    sql_expansion: CompiledSqlExpansion | None = field(default=None, compare=False, repr=False)
    lint_expansion: CompiledSqlExpansion | None = field(default=None, compare=False, repr=False)
    """The compile's whole expansion, variables included, which early SQL lint reuses."""


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
    fast_lineage_star_resolved: bool = False
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
    unchecked_output_columns: frozenset[str] = frozenset()
    rejected_sql_analysis_opt_out: SourceLocation | None = None

    @property
    def reference_rows(self) -> list[tuple[str, str, str | None, int | None]]:
        """Each reference as `(kind, name, package, call argument count)`."""

        return [
            (str(ref.ref_kind), ref.ref_name, ref.ref_package, ref.call_argument_count)
            for ref in self.references
        ]

    @property
    def relation_key_row(self) -> RelationKeyRow:
        """The model's declared key facts, for deriving its unique keys."""

        return _native.relation_key_row("ref", self.name, self.config.values, self.schema_entry)

    @property
    def key_row(self) -> tuple[str, str]:
        """`(resource type, name)` of the model's key."""

        return (str(self.key.resource_type), self.key.name)

    @property
    def dep_rows(self) -> list[tuple[str, str]]:
        """`(resource type, name)` of each dependency."""

        return [(str(dep.resource_type), dep.name) for dep in self.deps]

    @property
    def destination_row(self) -> tuple[str | None, str | None, str]:
        """`(database, schema, name)` of the model's destination."""

        return (self.destination.database, self.destination.schema, self.destination.name)

    @property
    def inferred_rows(self) -> list[tuple[str, str | None, str]] | None:
        """Each inferred column as `(name, type, nullability)`, or `None`."""

        if self.inferred_columns is None:
            return None
        return [
            (column.name, column.type, str(column.nullability)) for column in self.inferred_columns
        ]

    @property
    def schema_column_rows(self) -> list[tuple[str, str | None]] | None:
        """Each declared column of the attached schema as `(name, type)`, or `None`."""

        if self.schema_entry is None:
            return None
        return [(column.name, column.type) for column in self.schema_entry.columns]

    @property
    def has_dynamic_columns(self) -> bool:
        """Whether the attached schema declares dynamic columns."""

        return self.schema_entry is not None and bool(self.schema_entry.dynamic_columns)

    @property
    def output_column_count(self) -> int:
        """Inferred columns, else the attached schema's declared columns, else zero."""

        if self.inferred_columns is not None:
            return len(self.inferred_columns)
        return len(self.schema_entry.columns) if self.schema_entry is not None else 0


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
    binding_catalog: Any | None = field(default=None, repr=False, compare=False)
    effective_target_database: str | None = None
    effective_target_schema: str | None = None
    sql_analysis_dialect: str | None = None
    sql_lexical_syntax: SqlLexicalSyntax = field(default_factory=SqlLexicalSyntax)
    compile_cache_dir: Path | None = None
    settings: SettingsConfig = field(default_factory=SettingsConfig)
    scenario: ScenarioConfig = field(default_factory=ScenarioConfig)
    models: tuple[CompiledModelView, ...] = field(default_factory=tuple)
    sources: tuple[CompiledSourceView, ...] = field(default_factory=tuple)
    seeds: tuple[CompiledSeedView, ...] = field(default_factory=tuple)
    functions: tuple[CompiledFunctionView, ...] = field(default_factory=tuple)
    audits: tuple[CompiledAuditView, ...] = field(default_factory=tuple)
    sql_tests: tuple[CompiledSqlTest, ...] = field(default_factory=tuple)
    sql_scenarios: tuple[CompiledSqlScenario, ...] = field(default_factory=tuple)
    loader_functions: tuple[DiscoveredLoaderFunction, ...] = field(default_factory=tuple)
    hook_functions: tuple[DiscoveredHookFunction, ...] = field(default_factory=tuple)
    enforce_explicit_references: bool = True
    sql_hook_files: tuple[DiscoveredSqlHookFile, ...] = field(default_factory=tuple)
    materialization_files: tuple[DiscoveredMaterializationFile, ...] = field(default_factory=tuple)
    public_enums: dict[str, EnumDeclaration] = field(default_factory=dict)
    public_constants: dict[str, ConstantDeclaration] = field(default_factory=dict)
    loaded_macros: dict[str, LoadedMacro] = field(default_factory=dict)
    diagnostics: tuple[CompilerDiagnostic, ...] = field(default_factory=tuple)
    unmatched_literal_sql_relations: tuple[LiteralSqlRelation, ...] = field(default_factory=tuple)
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None
    scope_index: ScopeIndex = field(default_factory=ScopeIndex)
    sql_expansions: dict[Path, CompiledSqlExpansion] = field(
        default_factory=dict, compare=False, repr=False
    )
    native_session: Any | None = field(default=None, compare=False, repr=False)
    native_project: _native.NativeCompiledProject | None = field(
        default=None, compare=False, repr=False
    )

    @cached_property
    def lineage_graph(self) -> _native.NativeProjectGraph:
        """The lineage edges, tags, model folders and names, indexed natively once per project."""

        rows: list[tuple[tuple[str, str], list[tuple[str, str]], list[str], str | None]] = [
            (
                self._graph_key(model.key),
                self._graph_keys(model.deps),
                self._graph_tags(model.config.values.get("tags")),
                str(model.relative_path.parent),
            )
            for model in self.models
        ]
        rows.extend(
            (self._graph_key(source.key), self._graph_keys(source.deps), [], None)
            for source in self.sources
        )
        rows.extend(
            (
                self._graph_key(seed.key),
                self._graph_keys(seed.deps),
                list(seed.schema_entry.tags),
                None,
            )
            for seed in self.seeds
        )
        rows.extend(
            (
                self._graph_key(function.key),
                self._graph_keys(function.deps),
                list(function.tags),
                None,
            )
            for function in self.functions
        )
        return _native.NativeProjectGraph.from_resources(rows)

    @staticmethod
    def _graph_key(key: CompiledObjectKey) -> tuple[str, str]:
        return (str(key.resource_type), key.name)

    @classmethod
    def _graph_keys(cls, keys: Sequence[CompiledObjectKey]) -> list[tuple[str, str]]:
        return [cls._graph_key(key) for key in keys]

    @staticmethod
    def _graph_tags(value: object) -> list[str]:
        if isinstance(value, list | tuple):
            return [str(item) for item in value]
        return []


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
    read_helper_names: tuple[str, ...] = field(default_factory=tuple)
    reference_target_model_names: tuple[str, ...] = field(default_factory=tuple)
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
