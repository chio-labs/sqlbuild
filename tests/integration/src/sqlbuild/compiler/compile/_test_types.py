from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MacroBridgeParityTestCase:
    """A macro-heavy project and fragments its rendered compile inputs must contain."""

    description: str
    files: dict[str, str]
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class MacroBridgeMemoTestCase:
    """A project whose repeated macro calls run once per call class."""

    description: str
    files: dict[str, str]
    expected_native_executions: int


@dataclass(frozen=True)
class MacroBridgeFailureTestCase:
    """A project whose rendering fails with an expected error."""

    description: str
    files: dict[str, str]
    expected_message_fragment: str


@dataclass(frozen=True)
class MacroExpansionEdgeTestCase:
    """Hand-picked SQL texts whose expansion must match Python's expansion recorded in a golden."""

    description: str
    texts: tuple[str, ...]
    expected_mismatches: list[tuple[object, object, object]]


@dataclass(frozen=True)
class MacroExpansionDifferentialTestCase:
    """Seeded random SQL text that must expand, with and without the bridge, as Python's
    expansion recorded in its golden did."""

    description: str
    seed: int
    samples: int
    expected_minimum_successes: int
    expected_mismatches: list[tuple[object, object, object]]


@dataclass(frozen=True)
class FailingMacroProjectParityTestCase:
    """Seeded projects whose failing macros each raise one error."""

    description: str
    seed: int
    projects: int
    expected_minimum_failures: int
    expected_minimum_successes: int
    expected_minimum_errors_after_macro_runs: int
    expected_minimum_distinct_errors: int
