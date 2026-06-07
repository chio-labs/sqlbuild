from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.cli.commands.main.helpers.compile.types import CompileLineageMode


@dataclass(frozen=True)
class TargetWriterTestCase:
    description: str
    expected_files: dict[str, str] = field(default_factory=dict)
    initial_files: dict[str, str] = field(default_factory=dict)
    expected_summary_line: str = ""


@dataclass(frozen=True)
class CompileCommandTestCase:
    description: str
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
    model_sql: str | None = None


@dataclass(frozen=True)
class CompileDagArtifactTestCase:
    description: str
    dag_path: str
    expected_project_name: str
    expected_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class CompilePythonDagArtifactTestCase:
    description: str
    dag_path: str
    expected_project_name: str
    expected_node_ids: set[str]
    expected_edges: set[tuple[str, str]]
    expected_check_ids: set[str]


@dataclass(frozen=True)
class CompileTextOutputTestCase:
    description: str
    model_count: int
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompileTextColorTestCase:
    description: str
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CompileJsonExecutionLayersTestCase:
    description: str
    model_count: int
    expected_execution_layers: int


@dataclass(frozen=True)
class CompileJsonDiagnosticsTestCase:
    description: str
    model_sql: str
    expected_exit_code: int
    expected_code: str
    expected_severity: str
    expected_message: str
    expected_line: int
    expected_column: int


@dataclass(frozen=True)
class CompileLineageModeTestCase:
    description: str
    lineage_mode: CompileLineageMode
    expected_lineage_mode_values: tuple[str, ...]


@dataclass(frozen=True)
class ResolveAdapterTestCase:
    description: str
    adapter_name: str
    expected_adapter_class_name: str


@dataclass(frozen=True)
class ResolveAdapterErrorTestCase:
    description: str
    adapter_name: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ResolveEffectiveAdapterNameTestCase:
    description: str
    project_adapter: str
    local_adapter: str | None
    expected_adapter_name: str
