"""Structured models for discovered project inputs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.compiler.compile.constants import DEFAULT_SQL_TEST_MODE
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.discovery.types import LoaderConnectionMode
from sqlbuild.providers import Provider
from sqlbuild.python_nodes.models import ColumnLineageRef, RetryPolicy, SqlResourceRef
from sqlbuild.python_nodes.types import PythonCheckSeverity
from sqlbuild.spec.contracts.models import (
    LocalConfig,
    ProjectConfig,
    SchemaColumn,
    SchemaModelEntry,
    SchemaSeedEntry,
    SourceColumnEntry,
    SourceEntry,
    SourceLocation,
)
from sqlbuild.spec.contracts.types import SourceWriteStrategy


@dataclass(frozen=True)
class SqlHookEntry:
    """A model lifecycle hook that executes SQL."""

    statement: str
    name: str | None = None
    relative_path: Path | None = None
    definition_sql: str | None = None
    kwargs: dict[str, object] | None = None
    description: str | None = None


@dataclass(frozen=True)
class NamedSqlHookEntry:
    """An unresolved invocation of a discovered SQL hook resource."""

    name: str
    kwargs: dict[str, object]


@dataclass(frozen=True)
class PythonHookEntry:
    """A model lifecycle hook that invokes a discovered Python hook."""

    name: str
    kwargs: dict[str, object]


@dataclass(frozen=True)
class DiscoveredSqlModelFile:
    """A discovered SQL model file and its raw contents."""

    file_path: Path
    relative_path: Path
    contents: str
    header_values: dict[str, object]
    header_column_locations: dict[str, SourceLocation]
    output_column_locations: dict[str, SourceLocation]
    query_sql: str
    enum_declarations: tuple[EnumDeclaration, ...] = field(default_factory=tuple)
    constant_declarations: tuple[ConstantDeclaration, ...] = field(default_factory=tuple)
    output_column_locations_extracted: bool = True
    extract_implicit_alias_columns: bool = True


@dataclass(frozen=True)
class DiscoveredSqlFunctionFile:
    """A discovered SQL function file and its raw contents."""

    file_path: Path
    relative_path: Path
    contents: str
    header_values: dict[str, object]
    body_sql: str


@dataclass(frozen=True)
class DiscoveredSqlHookFile:
    """A discovered named SQL lifecycle hook resource."""

    file_path: Path
    relative_path: Path
    contents: str
    header_values: dict[str, object]
    sql_body: str
    name: str
    description: str | None = None


@dataclass(frozen=True)
class EnumMember:
    """One named member in a SQLBuild enum declaration."""

    name: str
    value: str | int


@dataclass(frozen=True)
class EnumDeclaration:
    """One validated public or model-local enum declaration."""

    name: str
    members: tuple[EnumMember, ...]
    scalar_type: str
    relative_path: Path
    model_name: str | None = None


@dataclass(frozen=True)
class ConstantDeclaration:
    """One validated public or model-local constant declaration."""

    name: str
    value: str | int
    scalar_type: str
    relative_path: Path
    model_name: str | None = None


@dataclass(frozen=True)
class DiscoveredEnumFile:
    """A public SQL file containing one or more enum declarations."""

    file_path: Path
    relative_path: Path
    contents: str
    declarations: tuple[EnumDeclaration, ...]


@dataclass(frozen=True)
class DiscoveredConstantFile:
    """A public SQL file containing one or more constant declarations."""

    file_path: Path
    relative_path: Path
    contents: str
    declarations: tuple[ConstantDeclaration, ...]


@dataclass(frozen=True)
class ModelSchemaDeclaration:
    """One public reusable model column schema declaration."""

    name: str
    columns: tuple[SchemaColumn, ...]
    relative_path: Path
    extends: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class DiscoveredModelSchemaFile:
    """A public SQL file containing reusable model schemas."""

    file_path: Path
    relative_path: Path
    contents: str
    declarations: tuple[ModelSchemaDeclaration, ...]


@dataclass(frozen=True)
class DiscoveredPythonFunctionFile:
    """A discovered Python function file and its parsed UDF metadata."""

    file_path: Path
    relative_path: Path
    contents: str
    header_values: dict[str, object]
    entry_point: str
    body_python: str


@dataclass(frozen=True)
class DiscoveredSchemaFile:
    """A discovered schema.yml file and its raw contents."""

    file_path: Path
    relative_path: Path
    contents: str
    model_entries: tuple[SchemaModelEntry, ...]
    seed_entries: tuple[SchemaSeedEntry, ...]


@dataclass(frozen=True)
class DiscoveredSourceFile:
    """A discovered source declaration file and its raw contents."""

    file_path: Path
    relative_path: Path
    contents: str
    source_entries: tuple[SourceEntry, ...]


@dataclass(frozen=True)
class DiscoveredSeedFile:
    """A discovered seed file."""

    file_path: Path
    relative_path: Path


@dataclass(frozen=True)
class DiscoveredSqlTestFile:
    """A discovered SQL-native test file and its raw contents."""

    file_path: Path
    relative_path: Path
    contents: str
    blocks: tuple[DiscoveredSqlTestBlock, ...]


@dataclass(frozen=True)
class DiscoveredSqlTestBlock:
    """One raw TEST(...) block discovered from a SQL-native test file."""

    test_index: int
    header_values: dict[str, object]
    sql_body: str
    name: str | None = None
    mode: SqlTestMode = DEFAULT_SQL_TEST_MODE


@dataclass(frozen=True)
class DiscoveredSqlScenarioFile:
    """A discovered SQL-native scenario file and its raw contents."""

    file_path: Path
    relative_path: Path
    contents: str
    header_values: dict[str, object]
    sql_body: str
    name: str


@dataclass(frozen=True)
class DiscoveredAuditFile:
    """A discovered audit SQL file and its raw contents."""

    file_path: Path
    relative_path: Path
    contents: str
    blocks: tuple[DiscoveredAuditBlock, ...]


@dataclass(frozen=True)
class DiscoveredAuditBlock:
    """One raw AUDIT(...) block discovered from a SQL audit file."""

    audit_index: int
    header_values: dict[str, object]
    sql_body: str
    name: str | None = None


@dataclass(frozen=True)
class DiscoveredMacroFile:
    """A discovered project macro file and its raw contents."""

    file_path: Path
    relative_path: Path
    contents: str


@dataclass(frozen=True)
class DiscoveredAdapterFile:
    """A detected project adapter Python file."""

    file_path: Path
    relative_path: Path


@dataclass(frozen=True)
class DiscoveredMaterializationFile:
    """A discovered custom materialization Python file."""

    file_path: Path
    relative_path: Path
    name: str
    provider_usages: tuple[DiscoveredProviderUsage, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiscoveredProviderUsage:
    """Framework-owned metadata for provider usage by a Python callable surface."""

    provider_name: str
    parameter_name: str
    annotation_class_name: str | None = None
    annotation_module: str | None = None


@dataclass(frozen=True)
class DiscoveredLoaderFunction:
    """A discovered project source loader function."""

    file_path: Path
    relative_path: Path
    name: str
    function: Callable[..., object]
    depends_on: tuple[Callable[..., object] | SqlResourceRef, ...] = field(default_factory=tuple)
    destination: str | None = None
    write_strategy: SourceWriteStrategy | None = None
    cursor_column: str | None = None
    unique_key: tuple[str, ...] = field(default_factory=tuple)
    columns: tuple[SourceColumnEntry, ...] = field(default_factory=tuple)
    contract: str | None = None
    connection_mode: LoaderConnectionMode = LoaderConnectionMode.SQLBUILD
    provider_usages: tuple[DiscoveredProviderUsage, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiscoveredTaskFunction:
    """A discovered project task function."""

    file_path: Path
    relative_path: Path
    name: str
    function: Callable[..., object]
    depends_on: tuple[Callable[..., object] | SqlResourceRef, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    group: str | None = None
    description: str | None = None
    meta: dict[str, object] | None = None
    retry: RetryPolicy | None = None
    provider_usages: tuple[DiscoveredProviderUsage, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiscoveredAssetFunction:
    """A discovered project asset function."""

    file_path: Path
    relative_path: Path
    name: str
    function: Callable[..., object]
    depends_on: tuple[Callable[..., object] | SqlResourceRef, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    group: str | None = None
    description: str | None = None
    meta: dict[str, object] | None = None
    columns: tuple[SourceColumnEntry, ...] = field(default_factory=tuple)
    column_lineage: dict[str, tuple[ColumnLineageRef, ...]] | None = None
    retry: RetryPolicy | None = None
    provider_usages: tuple[DiscoveredProviderUsage, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiscoveredCheckFunction:
    """A discovered project check function."""

    file_path: Path
    relative_path: Path
    name: str
    function: Callable[..., object]
    depends_on: tuple[Callable[..., object] | SqlResourceRef, ...]
    severity: PythonCheckSeverity = PythonCheckSeverity.ERROR
    tags: tuple[str, ...] = field(default_factory=tuple)
    group: str | None = None
    description: str | None = None
    meta: dict[str, object] | None = None
    provider_usages: tuple[DiscoveredProviderUsage, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiscoveredHookFunction:
    """A discovered project model lifecycle hook function."""

    file_path: Path
    relative_path: Path
    name: str
    function: Callable[..., object]
    description: str | None = None
    provider_usages: tuple[DiscoveredProviderUsage, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiscoveredProvider:
    """A discovered project provider class and validated settings object."""

    file_path: Path
    relative_path: Path
    name: str
    provider_class: type[Provider]
    settings: Provider


@dataclass(frozen=True)
class DiscoveredPythonNodeFunctions:
    """Discovered project Python DAG node functions grouped by kind."""

    loaders: tuple[DiscoveredLoaderFunction, ...] = field(default_factory=tuple)
    tasks: tuple[DiscoveredTaskFunction, ...] = field(default_factory=tuple)
    assets: tuple[DiscoveredAssetFunction, ...] = field(default_factory=tuple)
    checks: tuple[DiscoveredCheckFunction, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiscoveredProjectInputs:
    """All raw project inputs discovered from disk before semantic resolution."""

    project_config: ProjectConfig
    local_config: LocalConfig
    project_dir: Path | None = None
    model_files: tuple[DiscoveredSqlModelFile, ...] = field(default_factory=tuple)
    enum_files: tuple[DiscoveredEnumFile, ...] = field(default_factory=tuple)
    constant_files: tuple[DiscoveredConstantFile, ...] = field(default_factory=tuple)
    model_schema_files: tuple[DiscoveredModelSchemaFile, ...] = field(default_factory=tuple)
    sql_function_files: tuple[DiscoveredSqlFunctionFile, ...] = field(default_factory=tuple)
    sql_hook_files: tuple[DiscoveredSqlHookFile, ...] = field(default_factory=tuple)
    python_function_files: tuple[DiscoveredPythonFunctionFile, ...] = field(default_factory=tuple)
    schema_files: tuple[DiscoveredSchemaFile, ...] = field(default_factory=tuple)
    source_files: tuple[DiscoveredSourceFile, ...] = field(default_factory=tuple)
    seed_files: tuple[DiscoveredSeedFile, ...] = field(default_factory=tuple)
    test_files: tuple[DiscoveredSqlTestFile, ...] = field(default_factory=tuple)
    scenario_files: tuple[DiscoveredSqlScenarioFile, ...] = field(default_factory=tuple)
    audit_files: tuple[DiscoveredAuditFile, ...] = field(default_factory=tuple)
    macro_files: tuple[DiscoveredMacroFile, ...] = field(default_factory=tuple)
    materialization_files: tuple[DiscoveredMaterializationFile, ...] = field(default_factory=tuple)
    loader_functions: tuple[DiscoveredLoaderFunction, ...] = field(default_factory=tuple)
    task_functions: tuple[DiscoveredTaskFunction, ...] = field(default_factory=tuple)
    asset_functions: tuple[DiscoveredAssetFunction, ...] = field(default_factory=tuple)
    check_functions: tuple[DiscoveredCheckFunction, ...] = field(default_factory=tuple)
    hook_functions: tuple[DiscoveredHookFunction, ...] = field(default_factory=tuple)
    providers: tuple[DiscoveredProvider, ...] = field(default_factory=tuple)
    adapter_file: DiscoveredAdapterFile | None = None
