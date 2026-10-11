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
    expected_minimum_environment_reads: int


@dataclass(frozen=True)
class AssemblyDeferralTestCase:
    """A project whose model SQL Python rejects with a syntax error."""

    description: str
    files: dict[str, str]
    expected_error: str


@dataclass(frozen=True)
class EdgeAssemblyTestCase:
    """Projects whose assembly raises or reads Python-only values, against Python's golden."""

    description: str
    projects: tuple[tuple[str, dict[str, str], dict[str, object] | None], ...]
    expected_raised: int


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


@dataclass(frozen=True)
class GraphFactsTestCase:
    """A project whose assembly request carries each resource's project-graph facts."""

    description: str
    files: dict[str, str]
    expected_model_tags: tuple[list[str], ...]
    expected_seeds: list[tuple[str, list[str]]]
    expected_function_kinds: tuple[str, ...]


@dataclass(frozen=True)
class NativePanicTestCase:
    """A project whose native assembly panics in the parser."""

    description: str
    files: dict[str, str]
    dialect: str
    expected_message: str
