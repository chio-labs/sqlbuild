from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeneratedAssemblyParityTestCase:
    """Seeded generated projects whose resource assembly both engines must agree on."""

    description: str
    seed: int
    count: int
    model_count: int
    environment: dict[str, str]
    expected_minimum_python_calls: int
    expected_minimum_environment_reads: int


@dataclass(frozen=True)
class AssemblyDeferralTestCase:
    """A project Python rejects: native raises the same error, deferring only where recorded."""

    description: str
    files: dict[str, str]
    expected_kind: str | None
    expected_error: str


@dataclass(frozen=True)
class DeferredAssemblyTestCase:
    """A project native hands back to Python, which assembles it without error."""

    description: str
    effective_vars: dict[str, object]
    seed_schema: str
    expected_schema: str
    expected_kind: str


@dataclass(frozen=True)
class WindowsEnvironmentTestCase:
    """A seed schema reading ENV through a mapping that upper-cases keys, as Windows does."""

    description: str
    environment: dict[str, str]
    seed_schema: str
    expected_schema: str


@dataclass(frozen=True)
class OptOutTestCase:
    """Models opting out of required SQL analysis, and which ones parse so Python rejects them."""

    description: str
    models: dict[str, str]
    expected_rejected: dict[str, bool]
    expected_python_validations: int


@dataclass(frozen=True)
class GraphFactsTestCase:
    """A project whose assembly request carries each resource's project-graph facts."""

    description: str
    files: dict[str, str]
    expected_model_tags: tuple[list[str], ...]
    expected_seeds: list[tuple[str, list[str]]]
    expected_function_kinds: tuple[str, ...]
