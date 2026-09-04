from dataclasses import dataclass, field

from sqlbuild.executor.testing.types import SqlTestOutcome


@dataclass(frozen=True)
class SqlTestExecutionTestCase:
    """Test case for SQL unit test execution."""

    description: str
    chain_steps: tuple[tuple[str, str, str | None], ...]
    expected_outcome: SqlTestOutcome
    expected_step_count: int
    expected_failed_models: tuple[str, ...] = field(default_factory=tuple)
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class SqlTestComparisonSqlTestCase:
    """Test case for generated SQL unit-test comparison SQL."""

    description: str
    chain_steps: tuple[tuple[str, str, str | None], ...]
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SqlTestDifferenceSqlTestCase:
    """Test case for one dialect's bounded difference SQL."""

    description: str
    dialect: str
    expected_fragment: str
    unexpected_fragment: str


@dataclass(frozen=True)
class SqlTestDiagnosticsTestCase:
    """Test case for expected-output difference diagnostics."""

    description: str
    chain_steps: tuple[tuple[str, str, str | None], ...]
    expected_actual_count: int
    expected_expected_count: int
    expected_unexpected_count: int
    expected_missing_count: int
    expected_sample_count: int
    expect_redaction: bool = False
    expect_truncation: bool = False
