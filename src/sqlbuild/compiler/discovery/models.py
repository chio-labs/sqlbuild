"""Structured models for discovered project inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.spec.models.project import LocalConfig, ProjectConfig
from sqlbuild.spec.models.schema import SchemaModelEntry, SchemaSeedEntry
from sqlbuild.spec.models.source import SourceEntry


@dataclass(frozen=True)
class DiscoveredSqlModelFile:
    """A discovered SQL model file and its raw contents."""

    file_path: Path
    relative_path: Path
    contents: str
    header_values: dict[str, object]
    query_sql: str


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
class DiscoveredDbtManifestFile:
    """A discovered dbt manifest file and its raw JSON contents."""

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


@dataclass(frozen=True)
class DiscoveredProjectInputs:
    """All raw project inputs discovered from disk before semantic resolution."""

    project_config: ProjectConfig
    local_config: LocalConfig
    model_files: tuple[DiscoveredSqlModelFile, ...] = field(default_factory=tuple)
    schema_files: tuple[DiscoveredSchemaFile, ...] = field(default_factory=tuple)
    source_files: tuple[DiscoveredSourceFile, ...] = field(default_factory=tuple)
    seed_files: tuple[DiscoveredSeedFile, ...] = field(default_factory=tuple)
    test_files: tuple[DiscoveredSqlTestFile, ...] = field(default_factory=tuple)
    audit_files: tuple[DiscoveredAuditFile, ...] = field(default_factory=tuple)
    macro_files: tuple[DiscoveredMacroFile, ...] = field(default_factory=tuple)
    materialization_files: tuple[DiscoveredMaterializationFile, ...] = field(default_factory=tuple)
    dbt_manifest_file: DiscoveredDbtManifestFile | None = None
    adapter_file: DiscoveredAdapterFile | None = None
