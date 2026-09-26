"""Structured models for the lint and format layer."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from sqlbuild.compiler.compile.models import ExpansionSpan
from sqlbuild.lint.constants import VIOLATION_SEVERITY_FAULT, VIOLATION_SEVERITY_WARNING
from sqlbuild.lint.types import LintSeverity


@dataclass(frozen=True)
class HeaderSpan:
    """A located DSL header region inside one file."""

    kind: str
    start: int
    end: int


@dataclass(frozen=True)
class InterpolationSite:
    """One sqlbuild interpolation occurrence replaced by a unique sentinel."""

    sentinel: str
    neutralized_start: int
    neutralized_end: int
    original_start: int
    original_end: int
    original_text: str


@dataclass(frozen=True)
class LintBody:
    """One authored SQL body prepared for linting, with its expansion spans."""

    file_path: Path
    body_start: int
    body_end: int
    lint_text: str
    passes: tuple[tuple[ExpansionSpan, ...], ...]
    external_identifiers: tuple[str, ...] = ()
    dependency_identifiers: tuple[str, ...] = ()
    externally_referenced_ctes: tuple[str, ...] = ()
    allows_ceremonial_select: bool = False
    allows_dynamic_output_star: bool = False
    allows_empty_fixture_star: bool = False


@dataclass(frozen=True)
class FixtureNullCandidateScan:
    """Cheaply discovered SQL-test fixtures that may contain removable typed nulls."""

    paths: frozenset[Path] = field(default_factory=frozenset)
    model_names: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class LintEdit:
    """One deterministic authored-source edit proposed by a lint rule."""

    file_path: Path
    code: str
    start: int
    end: int
    replacement: str


@dataclass(frozen=True)
class LintViolation:
    """One lint diagnostic reported against an authored file."""

    file_path: Path
    line: int
    column: int
    code: str
    message: str
    severity: LintSeverity
    engine: str
    end_line: int | None = None
    end_column: int | None = None
    remediation: str | None = None
    fix: LintEdit | None = None
    fix_unavailable_reason: str | None = None


@dataclass(frozen=True)
class RuleFixResult:
    """One applied, refused, or unavailable semantic Rule fix."""

    file_path: Path
    code: str
    line: int
    status: Literal["applied", "refused", "unavailable"]
    reason: str


@dataclass(frozen=True)
class FormatChange:
    """One deterministic file-formatting change."""

    file_path: Path
    before: str
    after: str


@dataclass(frozen=True)
class LintConfig:
    """Resolved lint and format configuration for one run."""

    native_enabled: bool = True
    max_ranking_order_by: int = 4
    max_description_lines: int = 10
    line_width: int = 100
    dialect: str = "generic"
    enabled_native_rules: tuple[str, ...] | None = None
    ignored_native_rules: tuple[str, ...] = ()
    header_rules_enabled: bool = True


@dataclass(frozen=True)
class LintRunResult:
    """Aggregated outcome of one lint or format run."""

    files_checked: int
    violations: tuple[LintViolation, ...]
    formatted_files: tuple[Path, ...]
    format_changes: tuple[FormatChange, ...] = ()
    rule_fixes: tuple[RuleFixResult, ...] = ()
    source_texts: Mapping[Path, str] = field(default_factory=dict, repr=False, compare=False)

    @property
    def faults(self) -> tuple[LintViolation, ...]:
        """Return violations with fault severity."""

        return tuple(
            violation
            for violation in self.violations
            if violation.severity == VIOLATION_SEVERITY_FAULT
        )

    @property
    def warnings(self) -> tuple[LintViolation, ...]:
        """Return violations with warning severity."""

        return tuple(
            violation
            for violation in self.violations
            if violation.severity == VIOLATION_SEVERITY_WARNING
        )
