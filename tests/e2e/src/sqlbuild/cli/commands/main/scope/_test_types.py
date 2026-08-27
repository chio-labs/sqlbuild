"""Scope E2E test cases."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScopeE2eCase:
    description: str
    expected_exit_code: int


@dataclass(frozen=True)
class ScopePerformanceCase:
    description: str
    small_model_count: int
    small_domain_count: int
    large_model_count: int
    large_domain_count: int
    sample_count: int
    expected_max_small_seconds: float
    expected_max_large_seconds: float
    expected_max_warm_seconds: float
    expected_max_scaling_ratio: float
    expected_max_cache_bytes: int
    command_timeout_seconds: float


@dataclass(frozen=True)
class LargeScopePerformanceCase:
    description: str
    model_count: int
    domain_count: int
    warm_sample_count: int
    expected_max_cold_seconds: float
    expected_max_warm_seconds: float
    expected_max_cache_bytes: int
    command_timeout_seconds: float
