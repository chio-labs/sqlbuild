"""Test case types for format command performance guards."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleFixTestCase:
    description: str
    sql: str
    expected_status: str
    expected_code: str
    expected_returncode: int
    expected_unchanged: bool
    expected_with: bool


@dataclass(frozen=True)
class RuleFixPerformanceTestCase:
    description: str
    width: int
    depth: int
    expected_with: bool = False


@dataclass(frozen=True)
class FormatPerformanceGuardTestCase:
    """One generated format workload and its performance budgets."""

    description: str
    model_count: int
    test_count: int
    expected_test_file_count: int
    expected_typed_null_candidate_count: int
    expected_max_elapsed_seconds: float
    expected_max_format_seconds: float
    hard_ceiling_seconds: float
    expected_returncode: int
    additional_arguments: tuple[str, ...] = ()


@dataclass(frozen=True)
class FormatScalingGuardTestCase:
    """One doubling profile for selected format workloads."""

    description: str
    test_counts: tuple[int, ...]
    model_count: int
    expected_max_doubling_ratio: float
    expected_max_largest_elapsed_seconds: float
    hard_ceiling_seconds: float
    expected_returncode: int


@dataclass(frozen=True)
class ExampleProjectFormatTestCase:
    """One repository example project that formatting must leave semantically unchanged."""

    description: str
    relative_path: str
    expected_format_exit_code: int = 0


@dataclass(frozen=True)
class ModelFormatPerformanceTestCase:
    """One generated unformatted model workload and its format budgets."""

    description: str
    model_count: int
    large_model_lines: int
    expected_file_count: int
    expected_max_format_seconds: float
    expected_max_elapsed_seconds: float
    hard_ceiling_seconds: float
    expected_returncode: int = 1


@dataclass(frozen=True)
class ModelFormatScalingTestCase:
    """One doubling profile for unformatted model formatting."""

    description: str
    model_counts: tuple[int, ...]
    expected_max_doubling_ratio: float
    hard_ceiling_seconds: float
    expected_returncode: int = 1


@dataclass(frozen=True)
class TokenPreservationFormatTestCase:
    """One authored model and the exact text formatting must write for it."""

    description: str
    project_toml: str
    model_name: str
    authored_sql: str
    expected_sql: str


@dataclass(frozen=True)
class TokenPreservationBuildTestCase:
    """One authored model whose formatted form must build with exact column names and rows."""

    description: str
    authored_sql: str
    expected_sql: str
    expected_columns: list[str]
    expected_rows: list[tuple[object, ...]]
