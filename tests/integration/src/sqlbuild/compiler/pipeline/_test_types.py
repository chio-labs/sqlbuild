from __future__ import annotations

from dataclasses import dataclass, field


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
    append_cursor_inclusive: bool
    expected_resolved_sql_fragment: str


@dataclass(frozen=True)
class SqlglotChainCompileTargetIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    compiled_test_path: str
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class SnowflakeTargetValidationIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    expected_error_fragment: str
