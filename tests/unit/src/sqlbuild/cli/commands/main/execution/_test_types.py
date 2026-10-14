from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuildProcessReportTestCase:
    description: str
    error_type: type[BaseException]
    verbose: bool
    expected_fragments: tuple[str, ...]
    expected_absent_fragments: tuple[str, ...]


@dataclass(frozen=True)
class BuildDurationLimitTestCase:
    description: str
    project_toml: str
    remediation: str
    expected_code: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ScenarioCompilePresentationTestCase:
    description: str
    tty: bool
    expected_fragment: str
    unexpected_fragment: str
    expected_terminal: str
