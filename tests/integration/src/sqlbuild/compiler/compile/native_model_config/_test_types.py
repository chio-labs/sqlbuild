"""Test case types for the native model config build and validator parity tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelValidationParityTestCase:
    """Seeded effective configs validated natively and by the Python validators."""

    description: str
    seed: int
    count: int
    expected_minimum_native_accepted: int
    expected_minimum_python_rejected: int
    expected_minimum_acceptance_percent: int
    expected_minimum_error_percent: int


@dataclass(frozen=True)
class ModelConfigBuildParityTestCase:
    """Seeded defaults, path defaults, headers and targets built natively and in Python."""

    description: str
    seed: int
    count: int
    expected_minimum_built: int
    expected_minimum_python_raised: int
    expected_minimum_build_percent: int
    expected_minimum_error_percent: int


@dataclass(frozen=True)
class ModelConfigProjectTestCase:
    """A whole project compiled and built on DuckDB under one compiler engine."""

    description: str
    engine: str
    expected_models: tuple[str, ...]


@dataclass(frozen=True)
class NativeErrorParityTestCase:
    """An invalid config whose native outcome must be Python's exact error or a deferral."""

    description: str
    values: dict[str, object]
    expected_native_outcome: object
    expected_python_outcome: object
