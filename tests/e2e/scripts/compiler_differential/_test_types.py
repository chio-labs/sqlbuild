"""Test case types for the compiler differential harness end-to-end tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HarnessRunTestCase:
    """One harness run over a fixture and the report lines it must and must not print."""

    description: str
    extra_arguments: tuple[str, ...]
    expected_exit_code: int
    expected_lines: tuple[str, ...]
    expected_patterns: tuple[str, ...]
    expected_absent: tuple[str, ...]


@dataclass(frozen=True)
class ProjectExpectationTestCase:
    """A broken project run with one --expect value and the verdict the harness must reach."""

    description: str
    extra_arguments: tuple[str, ...]
    expected_exit_code: int
    expected_lines: tuple[str, ...]


@dataclass(frozen=True)
class DiscoveryCaptureTestCase:
    """A generated project with every feature block and what its discovery capture must hold."""

    description: str
    seed: int
    blocks: tuple[str, ...]
    expected_collections: frozenset[str]


@dataclass(frozen=True)
class FailureCorpusCodesTestCase:
    """The failure corpus run for real and the codes its cases must emit."""

    description: str
    expected_first_errors: dict[str, str]
    expected_warnings: dict[str, str]
    expected_discovery_codes: frozenset[str]


@dataclass(frozen=True)
class CoverageFailureTestCase:
    """A seed range too small for full coverage and how the harness must report it."""

    description: str
    extra_arguments: tuple[str, ...]
    expected_exit_code: int
    expected_lines: tuple[str, ...]
    expected_absent: tuple[str, ...]
