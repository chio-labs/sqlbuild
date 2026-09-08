"""Structured models for the lint and format layer."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.compiler.compile.models import ExpansionSpan
from sqlbuild.lint.constants import VIOLATION_SEVERITY_FAULT, VIOLATION_SEVERITY_WARNING
from sqlbuild.lint.types import CustomLintCheck, LintSeverity


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
class LintRuleOption[T]:
    """One typed option available to a custom statement-local lint rule."""

    name: str
    value_type: type[T]
    default: T
    description: str


@dataclass(frozen=True)
class CustomLintFinding:
    """One custom lint diagnostic over a plain SQL source span."""

    code: str
    start: int
    end: int
    message: str
    remediation: str


@dataclass(frozen=True)
class CustomLintRule:
    """Metadata and implementation for one custom SQL lint rule."""

    code: str
    family: str
    slug: str
    message: str
    remediation: str
    check: CustomLintCheck
    options: tuple[LintRuleOption[object], ...] = ()


@dataclass(frozen=True)
class FormatChange:
    """One deterministic file-formatting change."""

    file_path: Path
    before: str
    after: str


@dataclass(frozen=True)
class LintFixRecord:
    """One applied or skipped lint repair for human and machine reporting."""

    file_path: Path
    code: str
    line: int
    column: int
    status: str
    reason: str | None = None


@dataclass(frozen=True)
class LintConfig:
    """Resolved lint and format configuration for one run."""

    native_enabled: bool = True
    max_description_lines: int = 10
    dialect: str = "generic"
    enabled_native_rules: tuple[str, ...] | None = None
    ignored_native_rules: tuple[str, ...] = ()
    selected_custom_rules: tuple[str, ...] = ()
    ignored_custom_rules: tuple[str, ...] = ()
    custom_rule_paths: tuple[str, ...] = ()
    custom_rule_modules: tuple[str, ...] = ()
    custom_rule_options: dict[str, dict[str, object]] = field(default_factory=dict)


@dataclass(frozen=True)
class LintRunResult:
    """Aggregated outcome of one lint or format run."""

    files_checked: int
    violations: tuple[LintViolation, ...]
    formatted_files: tuple[Path, ...]
    format_changes: tuple[FormatChange, ...] = ()
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


@dataclass(frozen=True)
class FixRunResult:
    """Aggregated result of planning or applying native lint repairs."""

    files_checked: int
    violations: tuple[LintViolation, ...]
    changed_files: tuple[Path, ...]
    changes: tuple[FormatChange, ...]
    fixes: tuple[LintFixRecord, ...]
    source_texts: Mapping[Path, str] = field(default_factory=dict, repr=False, compare=False)

    @property
    def faults(self) -> tuple[LintViolation, ...]:
        return tuple(
            violation
            for violation in self.violations
            if violation.severity == VIOLATION_SEVERITY_FAULT
        )

    @property
    def warnings(self) -> tuple[LintViolation, ...]:
        return tuple(
            violation
            for violation in self.violations
            if violation.severity == VIOLATION_SEVERITY_WARNING
        )
