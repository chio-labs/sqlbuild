"""Test case types for the compiler differential harness end-to-end tests."""

from __future__ import annotations

from dataclasses import dataclass

from scripts.compiler_differential.models import FailureCase


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
class SharedAnalysisSeedTestCase:
    """A generated seed that must compile cleanly and reuse shared analyses."""

    description: str
    seed: int
    expected_lines: tuple[str, ...]
    expected_capture_sides: tuple[str, ...]
    expected_compile_exit_code: int
    expected_minimum_shareable_members: int
    expected_minimum_shared_reuse: int


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
    expected_first_messages: dict[str, str]
    expected_warnings: dict[str, str]
    expected_discovery_codes: frozenset[str]
    expected_render_codes: frozenset[str]
    unreachable_render_codes: frozenset[str]
    expected_first_helps: dict[str, str]
    expected_first_notes: dict[str, frozenset[str]]
    expected_first_locations: dict[str, tuple[int, int]]
    expected_code_orders: dict[str, tuple[str, ...]]
    expected_analysis_codes: frozenset[str]
    unreachable_analysis_codes: frozenset[str]


@dataclass(frozen=True)
class CoverageFailureTestCase:
    """A seed range too small for full coverage and how the harness must report it."""

    description: str
    extra_arguments: tuple[str, ...]
    expected_exit_code: int
    expected_lines: tuple[str, ...]
    expected_absent: tuple[str, ...]


@dataclass(frozen=True)
class RenderCaptureTestCase:
    """A generated project with every feature block and the render kinds its capture proves."""

    description: str
    seed: int
    blocks: tuple[str, ...]
    command: tuple[str, ...]
    expected_kinds: frozenset[str]


@dataclass(frozen=True)
class AnalysisCaptureTestCase:
    """A generated project, the commands it runs, and the analysis kinds their captures prove."""

    description: str
    seed: int
    blocks: tuple[str, ...]
    dialect: str | None
    commands: tuple[tuple[str, ...], ...]
    generated_command_count: int
    expected_kinds: frozenset[str]
    expected_absent: frozenset[str]


@dataclass(frozen=True)
class WheelSiteReportTestCase:
    """A harness run that records wheel sites, optionally with an injected native deferral."""

    description: str
    perturbation: str
    expected_lines: tuple[str, ...]
    expected_sites: frozenset[str]
    expected_deferrals: frozenset[str]


@dataclass(frozen=True)
class NativeFallbackGateTestCase:
    """A recorded allow-list, an edit or sabotage, and the verdict of the next checked run."""

    description: str
    perturbation: str
    appended_entries: str
    expected_exit_code: int
    expected_lines: tuple[str, ...]


@dataclass(frozen=True)
class GoldenOutputTestCase:
    """Goldens recorded for one project, an edit to them, and the check verdict."""

    description: str
    golden_edit: tuple[str, str]
    expected_exit_code: int
    expected_lines: tuple[str, ...]


@dataclass(frozen=True)
class EngineErrorCaseTestCase:
    """One shared all-engine error case from the failure corpus, holding its exact error."""

    description: str
    expected_error_case: FailureCase
