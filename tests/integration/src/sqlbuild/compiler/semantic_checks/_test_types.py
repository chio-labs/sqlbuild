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


@dataclass(frozen=True)
class GeneratedMetadataParityTestCase:
    """Seeded projects whose metadata checks Python and the native engine must agree on."""

    description: str
    seed: int
    count: int
    model_count: int
    dialects: tuple[str, ...]
    expected_minimum_native: int
    expected_minimum_families: dict[str, int]


@dataclass(frozen=True)
class SessionCompletionTestCase:
    """Seeded preview compiles whose completion reads analysed models from the native session."""

    description: str
    corpus: str
    seed: int
    count: int
    model_count: int
    expected_session_models: int
    expected_payload_models: int
    expected_proven_outputs: int
    expected_minimum_codes: dict[str, int]
