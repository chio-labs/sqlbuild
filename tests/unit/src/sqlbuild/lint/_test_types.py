"""Test case dataclasses for lint project and CLI unit tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LintBehaviorTestCase:
    """Identity for one non-tabular lint behavior test."""

    description: str
    expected_value: object


@dataclass(frozen=True)
class LintProjectTestCase:
    """Test case for run_lint over a synthetic project."""

    description: str
    files: dict[str, str]
    extra_files: dict[str, str] = field(default_factory=dict)
    expected_fault_codes: tuple[tuple[str, str], ...] = ()
    expected_files_checked: int = 1


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
    extra_arguments: tuple[str, ...] = ()
    expected_output_fragments: tuple[str, ...] = ()
    expected_file_fragments: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FormatCliTestCase:
    """Test case for the sqb format command."""

    description: str
    files: dict[str, str]
    expected_exit_code: int
    extra_arguments: tuple[str, ...] = ()
    expected_output_fragments: tuple[str, ...] = ()
    expected_file_fragments: dict[str, str] = field(default_factory=dict)


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
