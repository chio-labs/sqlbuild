from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AuditFactoryCompileIntegrationTestCase:
    description: str
    expected_audit_count: int


@dataclass(frozen=True)
class MeasurementCompileIntegrationTestCase:
    description: str
    expected_minimum_samples: int
    expected_severity: str


@dataclass(frozen=True)
class MeasurementCompileErrorIntegrationTestCase:
    description: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ExpectedModelEntry:
    description: str
    expected_resolved_sql_fragment: str
    expected_logical_ddl_fragment: str
    expected_manifest_compiled_code_fragment: str


@dataclass(frozen=True)
class RunCompilePipelineIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    expected_models: dict[str, ExpectedModelEntry] = field(default_factory=dict)
    expected_model_count: int = 0
    expected_seed_count: int = 0
    expected_manifest_node_count: int = 0


@dataclass(frozen=True)
class SelectionLineageIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    select: tuple[str, ...]
    expected_selected_names: frozenset[str]
    expected_unselected_names: frozenset[str]


@dataclass(frozen=True)
class MacroLoadCountIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    expected_macro_import_count: int
    expected_declaration_resolution_count: int


@dataclass(frozen=True)
class MacroCompositionIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    macro_name: str
    expected_dependencies: tuple[str, ...]
    expected_declaration_resolution_count: int


@dataclass(frozen=True)
class CompileProgressIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    expected_progress_prefixes: tuple[str, ...]


@dataclass(frozen=True)
class DeferToIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    defer_to: str
    select: tuple[str, ...]
    expected_model_count: int
    expected_resolved_sql_fragments: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DiffSelectorIntegrationTestCase:
    description: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_model_names: frozenset[str]


@dataclass(frozen=True)
class AppendCursorPipelineIntegrationTestCase:
    description: str
    model_header_cursor_config: str
    expected_resolved_sql_fragment: str


@dataclass(frozen=True)
class SqlAnalysisChainCompileTargetIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    compiled_test_path: str
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class SnowflakeTargetValidationIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    expected_error_fragment: str = ""
    expected_database: str | None = None
    expected_schema: str | None = None
