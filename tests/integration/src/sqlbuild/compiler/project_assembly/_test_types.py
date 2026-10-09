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
    """A project native hands back to Python, recording why, with Python's exact outcome."""

    description: str
    files: dict[str, str]
    expected_kind: str
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
