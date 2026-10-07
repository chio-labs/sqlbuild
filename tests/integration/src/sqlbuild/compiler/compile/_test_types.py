from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MacroBridgeParityTestCase:
    """A macro-heavy project both engines must render to identical compile inputs."""

    description: str
    files: dict[str, str]
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class MacroBridgeMemoTestCase:
    """A project whose repeated macro calls run once per call class under the native engine."""

    description: str
    files: dict[str, str]
    expected_python_executions: int
    expected_native_executions: int


@dataclass(frozen=True)
class MacroBridgeFailureTestCase:
    """A project whose rendering fails identically under both engines."""

    description: str
    files: dict[str, str]
    expected_message_fragment: str


@dataclass(frozen=True)
class MacroExpansionDifferentialTestCase:
    """Seeded random SQL text that must expand identically with and without the bridge."""

    description: str
    seed: int
    samples: int
    expected_minimum_successes: int
    expected_mismatches: list[tuple[object, object, object]]
