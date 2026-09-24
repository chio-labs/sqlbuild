"""Test types for test command e2e tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SqlTestE2ETestCase:
    """Test case for sqb test e2e verification."""

    description: str
    expected_exit_code: int
    expected_stdout_fragment: str
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_ordered_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SqlAnalysisChainSqlTestE2ETestCase:
    """Test case for SQL analysis SQL unit-test chain execution and artifacts."""

    description: str
    sql_analysis_enabled: bool
    expected_artifact_fragments: tuple[str, ...]
    unexpected_artifact_fragments: tuple[str, ...]


@dataclass(frozen=True)
class ParameterCaseSelectionE2ETestCase:
    """Test case for one parameterized SQL-test case selection."""

    description: str
    case_name: str
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_stderr_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SqlTestPlanInspectionE2ETestCase:
    """Test case for offline SQL-test plan inspection."""

    description: str
    repo_files: dict[str, str]
    expected_stdout_fragments: tuple[str, ...]
    expected_exit_code: int = 0
    unexpected_stdout_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class SqlTestFixtureValidationE2ETestCase:
    """Test case for static SQL-test fixture validation."""

    description: str
    repo_files: dict[str, str]
    expected_stderr_fragments: tuple[str, ...]


@dataclass(frozen=True)
class ComplexValuesFixtureE2ETestCase:
    """Test case for complex string literals inside VALUES fixtures."""

    description: str
    adapter_name: str
    command: tuple[str, ...]
    expected_stdout_fragment: str


@dataclass(frozen=True)
class FixtureCompatibilityE2ETestCase:
    """Test case for valid fixture shapes that require conservative analysis."""

    description: str
    repo_files: dict[str, str]
    expected_stdout_fragment: str


@dataclass(frozen=True)
class PartialFixtureE2ETestCase:
    """Test case for implicit schema-aware partial relation fixtures."""

    description: str
    repo_files: dict[str, str]
    expected_stdout_fragment: str
    expected_artifact_fragments: tuple[str, ...]
    unexpected_artifact_fragments: tuple[str, ...] = field(default_factory=tuple)
    artifact_filename: str = "test_orders.sql"


@dataclass(frozen=True)
class SqlTestInspectConflictE2ETestCase:
    """Test case for mutually exclusive inspection output modes."""

    description: str
    expected_exit_code: int
    expected_stderr_fragment: str


@dataclass(frozen=True)
class TableFunctionFixtureE2ETestCase:
    """Test case for model-mode table-function fixture execution."""

    description: str
    expected_stdout_fragment: str
    expected_artifact_fragments: tuple[str, ...]
    unexpected_artifact_fragments: tuple[str, ...]


@dataclass(frozen=True)
class UnknownTableFunctionFixtureE2ETestCase:
    """Test case for rejecting an unknown model-mode table-function fixture."""

    description: str
    expected_stderr_fragment: str


@dataclass(frozen=True)
class SharedGraphChainE2ETestCase:
    """Test case for chained SQL tests over a shared (diamond) upstream graph."""

    description: str
    sql_analysis_enabled: bool
    expected_stdout_fragments: tuple[str, ...]
    once_rendered_fragments: tuple[str, ...]


@dataclass(frozen=True)
class SharedGraphMissingMockE2ETestCase:
    """Test case for one missing mock reached on every path of a deep shared graph."""

    description: str
    layers: int
    expected_error: str
    expected_stdout_fragments: tuple[str, ...]


@dataclass(frozen=True)
class ExpectedColumnSubsetE2ETestCase:
    """Test case for SQL tests that compare only the expected CTE's listed columns."""

    description: str
    sql_analysis_enabled: bool
    command: tuple[str, ...]
    expected_tests: dict[str, str]
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]
    unexpected_output_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class MissingMockCliE2ETestCase:
    """Test case for planning errors reported by plain test and compile commands."""

    description: str
    expected_error: str
    compile_error_line: str
    compile_summary_fragment: str
