"""Data models used by the compile command path."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands.types import CompileLineageMode
from sqlbuild.cli.output.models import WrittenTarget
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompilerDiagnostic
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.lineage.models import ProjectColumnLineage
from sqlbuild.compiler.pipeline.models import ProjectGraph


@dataclass(frozen=True)
class CompileProfileFlags:
    """Profiling toggles that skip compile phases for benchmarking."""

    skip_discovery_sql_analysis: bool = False
    skip_column_inference: bool = False
    skip_contracts: bool = False
    skip_write: bool = False


@dataclass(frozen=True)
class CompileCommandRequest:
    """CLI inputs for one `sqb compile` invocation."""

    project_dir: Path | None = None
    no_sql_validation: bool = False
    defer_to: str | None = None
    selected_target: str | None = None
    json_output: bool = False
    manifest: bool = False
    dag_path: str | None = None
    no_color: bool = False
    lineage_mode: CompileLineageMode = CompileLineageMode.FAST
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    cli_vars: dict[str, object] | None = None
    profile_flags: CompileProfileFlags = CompileProfileFlags()
    no_cache: bool = False


@dataclass(frozen=True)
class CompileAnalysis:
    """Compiled project analysis shared by compile output phases."""

    discovered_inputs: DiscoveredProjectInputs
    adapter: BaseAdapter
    graph: ProjectGraph
    selected_keys: frozenset[CompiledObjectKey]
    lineage: ProjectColumnLineage | None
    diagnostics: tuple[CompilerDiagnostic, ...]
    discover_ms: int
    graph_ms: int
    lineage_ms: int
    contract_ms: int
    built_in_rules_ms: int = 0
    custom_rules_ms: int = 0
    rule_cache_hits: int = 0
    rule_cache_misses: int = 0


@dataclass(frozen=True)
class CompileWriteResult:
    """Result of writing compiled artifacts with its elapsed time."""

    written: WrittenTarget
    write_ms: int


@dataclass(frozen=True)
class SqlTestArtifactCacheRecord:
    """Validated metadata for one previously written SQL test artifact."""

    identity: str
    relative_path: Path
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class SqlTestArtifactIdentityContext:
    """Project-wide identity fragments shared by every SQL test."""

    common_identity: str
    model_identities: dict[str, str]
