"""Pre-semantic compile input models built from discovered inputs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
    CompiledResourceType,
    SqlReferenceKind,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredAuditBlock,
    DiscoveredAuditFile,
    DiscoveredProjectInputs,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
    DiscoveredSqlModelFile,
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestFile,
)
from sqlbuild.spec.models.project import (
    EnvironmentConfig,
    LocalConfig,
    ProjectConfig,
    SettingsConfig,
)
from sqlbuild.spec.models.schema import SchemaModelEntry, SchemaSeedEntry
from sqlbuild.spec.models.source import SourceEntry


@dataclass(frozen=True)
class InferredColumn:
    """One output column inferred from query SQL via sqlglot parsing."""

    name: str
    type: str | None = None


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
class CompileSqlReference:
    """One logical SQL reference discovered from compiled SQL text."""

    ref_kind: SqlReferenceKind | str
    ref_name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref_kind", SqlReferenceKind(self.ref_kind))


@dataclass(frozen=True)
class CompiledObjectKey:
    """Stable logical identity for one compiled resource or external dependency."""

    resource_type: CompiledResourceType | str
    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource_type", CompiledResourceType(self.resource_type))


@dataclass(frozen=True)
class CompileSqlTestCte:
    """One top-level SQL-native test CTE extracted after macro expansion."""

    name: str
    sql_body: str


@dataclass(frozen=True)
class CompileSqlTestCtes:
    """Extracted top-level SQL-native test CTE semantics."""

    authored_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
    macro_mocks: dict[str, str] = field(default_factory=dict)
    mock_model_names: tuple[str, ...] = field(default_factory=tuple)
    mock_source_names: tuple[str, ...] = field(default_factory=tuple)
    expected_model_names: tuple[str, ...] = field(default_factory=tuple)


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
class CompileSqlTestInput:
    """One discovered SQL-native test block with compile-time SQL expansion applied."""

    test_file: DiscoveredSqlTestFile
    test_block: DiscoveredSqlTestBlock
    sql_body: str
    authored_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
    macro_mocks: dict[str, str] = field(default_factory=dict)
    mock_model_names: tuple[str, ...] = field(default_factory=tuple)
    mock_source_names: tuple[str, ...] = field(default_factory=tuple)
    expected_model_names: tuple[str, ...] = field(default_factory=tuple)


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
    effective_environment_name: str | None = None
    effective_environment: EnvironmentConfig | None = None
    effective_connection: dict[str, object] = field(default_factory=dict)
    effective_vars: dict[str, str] = field(default_factory=dict)
    loaded_macros: dict[str, LoadedMacro] = field(default_factory=dict)
    model_inputs: tuple[CompileModelInput, ...] = field(default_factory=tuple)
    seed_inputs: tuple[CompileSeedInput, ...] = field(default_factory=tuple)
    source_inputs: tuple[CompileSourceInput, ...] = field(default_factory=tuple)
    test_inputs: tuple[CompileSqlTestInput, ...] = field(default_factory=tuple)
    audit_inputs: tuple[CompileAuditInput, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompiledRelationTarget:
    """Logical and physical target naming resolved during compile."""

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
    target: CompiledRelationTarget
    references: tuple[CompileSqlReference, ...] = field(default_factory=tuple)
    schema_entry: SchemaModelEntry | None = None
    inferred_columns: tuple[InferredColumn, ...] | None = None


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
    target: CompiledRelationTarget


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


@dataclass(frozen=True)
class CompiledSqlTest:
    """Compiled SQL-native unit test metadata selected by expected targets."""

    key: CompiledObjectKey
    scope_deps: tuple[CompiledObjectKey, ...]
    name: str
    test_file: DiscoveredSqlTestFile
    test_block: DiscoveredSqlTestBlock
    sql_body: str
    authored_ctes: tuple[CompileSqlTestCte, ...] = field(default_factory=tuple)
    macro_mocks: dict[str, str] = field(default_factory=dict)
    model_query_overrides: dict[str, str] = field(default_factory=dict)
    mock_model_names: tuple[str, ...] = field(default_factory=tuple)
    mock_source_names: tuple[str, ...] = field(default_factory=tuple)
    expected_model_names: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompiledProject:
    """Planner-ready whole-project compile output."""

    run_id: str
    effective_environment_name: str | None
    effective_connection: dict[str, object]
    effective_vars: dict[str, str]
    settings: SettingsConfig = field(default_factory=SettingsConfig)
    models: tuple[CompiledModel, ...] = field(default_factory=tuple)
    sources: tuple[CompiledSource, ...] = field(default_factory=tuple)
    seeds: tuple[CompiledSeed, ...] = field(default_factory=tuple)
    audits: tuple[CompiledAudit, ...] = field(default_factory=tuple)
    sql_tests: tuple[CompiledSqlTest, ...] = field(default_factory=tuple)
