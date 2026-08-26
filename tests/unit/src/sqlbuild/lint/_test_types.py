"""Test case dataclasses for lint project and CLI unit tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LintProjectTestCase:
    """Test case for run_lint over a synthetic project."""

    description: str
    files: dict[str, str]
    sqruff_enabled: bool = False
    extra_files: dict[str, str] = field(default_factory=dict)
    expected_fault_codes: tuple[tuple[str, str], ...] = ()
    expected_files_checked: int = 1
    expected_sqruff_engine_fault: bool = False


@dataclass(frozen=True)
class FormatProjectTestCase:
    """Test case for run_format over a synthetic project."""

    description: str
    files: dict[str, str]
    expected_written_fragments: dict[str, str] = field(default_factory=dict)
    expected_fault_codes: tuple[str, ...] = ()
    expected_formatted_count: int = 0


@dataclass(frozen=True)
class FormatNewlineTestCase:
    """Test case for preserving newline conventions while formatting."""

    description: str
    contents: bytes
    expected_newline: bytes


@dataclass(frozen=True)
class LintCliTestCase:
    """Test case for the sqb lint command."""

    description: str
    files: dict[str, str]
    expected_exit_code: int
    extra_arguments: tuple[str, ...] = ("--no-sqruff",)
    expected_output_fragments: tuple[str, ...] = ()
    expected_file_fragments: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FormatCliTestCase:
    """Test case for the sqb format command."""

    description: str
    files: dict[str, str]
    expected_exit_code: int
    extra_arguments: tuple[str, ...] = ("--no-sqruff",)
    expected_output_fragments: tuple[str, ...] = ()
    expected_file_fragments: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TranslateDialectTestCase:
    """Test case for adapter-to-sqruff dialect translation."""

    description: str
    adapter: str
    expected_dialect: str | None


@dataclass(frozen=True)
class SqruffScaffoldCreateTestCase:
    """Test case for scaffolding a sqruff config that does not yet exist."""

    description: str
    project_adapter: str
    expected_final_config: str


@dataclass(frozen=True)
class SqruffScaffoldExistingTestCase:
    """Test case for leaving an existing sqruff config untouched."""

    description: str
    project_adapter: str
    existing_config: str
    expected_warning: str | None


@dataclass(frozen=True)
class SqruffScaffoldDisabledTestCase:
    """Test case for scaffolding suppressed by disabled sqruff."""

    description: str
    project_adapter: str
    expected_config_exists: bool
    expected_warning: str | None


@dataclass(frozen=True)
class ExpandedLintTestCase:
    """Test case for linting the SQL a project actually produces."""

    description: str
    project_files: dict[str, str]
    expected_positions: tuple[tuple[int, int], ...]
    expected_message_fragments: tuple[str, ...]


@dataclass(frozen=True)
class LintCompileFailureTestCase:
    """Test case for a project that cannot compile and therefore cannot be linted."""

    description: str
    project_files: dict[str, str]
    expected_message_fragment: str


@dataclass(frozen=True)
class ExpandedTypedConstantTestCase:
    description: str
    project_files: dict[str, str]
    model_path: str
    authored_sql: str
    expected_sql: str
