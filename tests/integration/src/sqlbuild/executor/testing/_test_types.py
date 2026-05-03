from dataclasses import dataclass, field

from sqlbuild.executor.testing.types import SqlTestOutcome


@dataclass(frozen=True)
class SqlTestExecutionTestCase:
    """Test case for SQL unit test execution."""

    description: str
    chain_steps: tuple[tuple[str, str, str], ...]
    expected_outcome: SqlTestOutcome
    expected_step_count: int
    expected_failed_models: tuple[str, ...] = field(default_factory=tuple)
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class SqlTestComparisonSqlTestCase:
    """Test case for generated SQL unit-test comparison SQL."""

    description: str
    chain_steps: tuple[tuple[str, str, str], ...]
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = field(default_factory=tuple)
