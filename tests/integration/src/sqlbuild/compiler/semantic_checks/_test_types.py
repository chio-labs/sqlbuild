from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeneratedSemanticParityTestCase:
    """Seeded failing projects whose semantic completion Python and the native engine agree on."""

    description: str
    seed: int
    count: int
    model_count: int
    dialects: tuple[str, ...]
    expected_minimum_native_completions: int
    expected_minimum_native_diagnostics: int
    expected_minimum_type_recovery_plans: int
    expected_minimum_codes: dict[str, int]


@dataclass(frozen=True)
class DeferredSemanticTestCase:
    """A project the native stage hands back to Python, which records the deferral."""

    description: str
    dialect: str
    keeps_catalog: bool
    non_ascii_comment: bool
    expected_kinds: tuple[tuple[str, str], ...]
