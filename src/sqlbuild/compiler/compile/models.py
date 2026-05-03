"""Pre-semantic compile input models built from discovered inputs."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
    DiscoveredSqlModelFile,
)
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig
from sqlbuild.spec.models.schema import SchemaModelEntry, SchemaSeedEntry
from sqlbuild.spec.models.source import SourceEntry


@dataclass(frozen=True)
class CompileModelInput:
    """One discovered model file with its attached schema metadata, if any."""

    model_file: DiscoveredSqlModelFile
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
class CompileProjectInputs:
    """Attached project view used as the first pre-semantic compile input snapshot."""

    project_config: ProjectConfig
    local_config: LocalConfig
    discovered_inputs: DiscoveredProjectInputs
    model_inputs: tuple[CompileModelInput, ...] = field(default_factory=tuple)
    seed_inputs: tuple[CompileSeedInput, ...] = field(default_factory=tuple)
    source_inputs: tuple[CompileSourceInput, ...] = field(default_factory=tuple)
