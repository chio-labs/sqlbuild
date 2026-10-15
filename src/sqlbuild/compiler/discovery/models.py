"""Structured models for discovered project inputs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild._native import (
    CollectionRendering,
    DiscoveredAdapterFile,
    DiscoveredAuditFile,
    DiscoveredConstantFile,
    DiscoveredEnumFile,
    DiscoveredModelSchemaFile,
    DiscoveredPythonFunctionFile,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSqlFunctionFile,
    DiscoveredSqlHookFile,
    DiscoveredSqlModelFile,
    DiscoveredSqlTestBlock,
    EnumMember,
    NativeDiscoverySession,
)
from sqlbuild.compiler.discovery.constants import (
    SQL_SCENARIOS_OWNERSHIP_ROOT,
    SQL_TESTS_OWNERSHIP_ROOT,
)
from sqlbuild.compiler.discovery.types import (
    LoaderConnectionMode,
    ProjectProvider,
)
from sqlbuild.compiler.scopes.types import ScopeKind
from sqlbuild.python_nodes.models import AuditCase, ColumnLineageRef, RetryPolicy, SqlResourceRef
from sqlbuild.python_nodes.types import PythonCheckSeverity
from sqlbuild.runtime.event_exporting.constants import EVENT_EXPORT_KINDS
from sqlbuild.runtime.output_capture.types import CommandOutputStream
from sqlbuild.spec.contracts.models import (
    LocalConfig,
    ProjectConfig,
    SourceColumnEntry,
    SourceEntry,
)
from sqlbuild.spec.contracts.types import EventExportSeverity, SourceWriteStrategy
from sqlbuild.sql_values.models import SqlLogicalType, SqlValue
from sqlbuild.sql_values.types import SqlValueKind


@dataclass(frozen=True)
class SqlHookEntry:
    """A model lifecycle hook that executes SQL."""

    statement: str
    name: str | None = None
    relative_path: Path | None = None
    definition_sql: str | None = None
    kwargs: dict[str, object] | None = None
    description: str | None = None
    reads: tuple[SqlResourceRef, ...] = ()


@dataclass(frozen=True)
class PythonHookEntry:
    """A model lifecycle hook that invokes a discovered Python hook."""

    name: str
    kwargs: dict[str, object]


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
    value: SqlValue
    relative_path: Path
    model_name: str | None = None
    render_as: CollectionRendering | None = None

    @property
    def logical_type(self) -> SqlLogicalType:
        """Return the normalized logical type."""

        return self.value.logical_type

    @property
    def scalar_type(self) -> str:
        """Retain the existing SQL scalar type label for scalar declarations."""

        names: dict[SqlValueKind, str] = {
            SqlValueKind.STRING: "VARCHAR",
            SqlValueKind.INTEGER: "INTEGER",
            SqlValueKind.BOOLEAN: "BOOLEAN",
            SqlValueKind.FLOAT: "FLOAT",
            SqlValueKind.DECIMAL: "DECIMAL",
            SqlValueKind.NULL: "NULL",
        }
        return names.get(self.value.kind, self.value.logical_type.display_name.upper())


@dataclass(frozen=True)
class DiscoveredSourceFile:
    """A discovered source declaration file and its raw contents."""

    file_path: Path
    relative_path: Path
    contents: str
    source_entries: tuple[SourceEntry, ...]


@dataclass(frozen=True)
class DiscoveredSqlTestFile:
    """A discovered SQL-native test file and its raw contents."""

    file_path: Path
    relative_path: Path
    contents: str
    blocks: tuple[DiscoveredSqlTestBlock, ...]
    ownership_root: Path = Path(SQL_TESTS_OWNERSHIP_ROOT)


@dataclass(frozen=True)
class SqlTestParameterDeclaration:
    """One typed parameter declared by a SQL-native test template."""

    name: str
    value_type: SqlValueKind
    nullable: bool = False


@dataclass(frozen=True)
class DiscoveredSqlScenarioFile:
    """A discovered SQL-native scenario file and its raw contents."""

    file_path: Path
    relative_path: Path
    contents: str
    header_values: dict[str, object]
    sql_body: str
    name: str
    ownership_root: Path = Path(SQL_SCENARIOS_OWNERSHIP_ROOT)
    sql_body_span: tuple[int, int] | None = None


@dataclass(frozen=True)
class DiscoveredMacroFile:
    """A discovered project macro file and its raw contents."""

    file_path: Path
    relative_path: Path
    contents: str
    scope_kind: ScopeKind = ScopeKind.GLOBAL
    ownership_root: Path | None = None
    owning_path: Path | None = None
    declaration_root: Path | None = None


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
    description: str | None = None
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
    reads: tuple[SqlResourceRef, ...] = field(default_factory=tuple)
    provider_usages: tuple[DiscoveredProviderUsage, ...] = field(default_factory=tuple)
    scope_kind: ScopeKind = ScopeKind.GLOBAL
    ownership_root: Path | None = None
    owning_path: Path | None = None
    declaration_root: Path | None = None


@dataclass(frozen=True)
class DiscoveredAuditFactory:
    """A discovered audit factory and its normalized cases."""

    name: str
    function: Callable[..., object]
    file_path: Path
    relative_path: Path
    line: int
    cases: tuple[AuditCase, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiscoveredEventExporterDeclaration:
    """A discovered exporter declaration before provider binding."""

    file_path: Path
    relative_path: Path
    name: str
    function: Callable[..., object]
    event_kinds: frozenset[str]
    min_severity: EventExportSeverity


@dataclass(frozen=True)
class DiscoveredEventExporter:
    """A discovered canonical lifecycle event exporter function."""

    file_path: Path
    relative_path: Path
    name: str
    function: Callable[..., object]
    event_kinds: frozenset[str] = EVENT_EXPORT_KINDS
    min_severity: EventExportSeverity = EventExportSeverity.DEBUG
    provider_usages: tuple[DiscoveredProviderUsage, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiscoveredCommandOutputSinkDeclaration:
    """A command-output sink declaration before provider binding."""

    file_path: Path
    relative_path: Path
    name: str
    function: Callable[..., object]
    streams: frozenset[CommandOutputStream]


@dataclass(frozen=True)
class DiscoveredCommandOutputSink:
    """A discovered command-output sink function."""

    file_path: Path
    relative_path: Path
    name: str
    function: Callable[..., object]
    streams: frozenset[CommandOutputStream]
    provider_usages: tuple[DiscoveredProviderUsage, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiscoveredProvider:
    """A discovered project provider class and validated settings object."""

    file_path: Path
    relative_path: Path
    name: str
    provider_class: type[ProjectProvider]
    settings: ProjectProvider


@dataclass(frozen=True)
class DiscoveredPythonNodeFunctions:
    """Discovered project Python DAG node functions grouped by kind."""

    loaders: tuple[DiscoveredLoaderFunction, ...] = field(default_factory=tuple)
    tasks: tuple[DiscoveredTaskFunction, ...] = field(default_factory=tuple)
    assets: tuple[DiscoveredAssetFunction, ...] = field(default_factory=tuple)
    checks: tuple[DiscoveredCheckFunction, ...] = field(default_factory=tuple)
    audit_factories: tuple[DiscoveredAuditFactory, ...] = field(default_factory=tuple)


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
    audit_factories: tuple[DiscoveredAuditFactory, ...] = field(default_factory=tuple)
    hook_functions: tuple[DiscoveredHookFunction, ...] = field(default_factory=tuple)
    event_exporters: tuple[DiscoveredEventExporter, ...] = field(default_factory=tuple)
    command_output_sinks: tuple[DiscoveredCommandOutputSink, ...] = field(default_factory=tuple)
    providers: tuple[DiscoveredProvider, ...] = field(default_factory=tuple)
    adapter_file: DiscoveredAdapterFile | None = None
    native_session: NativeDiscoverySession | None = field(default=None, compare=False, repr=False)
    """The native session that read these declaration files, for later native stages.

    `None` means no session: readers must use the Python objects. Any copy that changes a
    discovered collection must set it to `None` so it never describes other files.
    """


@dataclass(frozen=True)
class DiscoveredRuntimeExtensions:
    """Command-startup providers, typed sinks, and lifecycle delivery settings."""

    providers: tuple[DiscoveredProvider, ...] = field(default_factory=tuple)
    event_exporters: tuple[DiscoveredEventExporter, ...] = field(default_factory=tuple)
    command_output_sinks: tuple[DiscoveredCommandOutputSink, ...] = field(default_factory=tuple)
    lifecycle_shutdown_timeout_seconds: int | None = None
