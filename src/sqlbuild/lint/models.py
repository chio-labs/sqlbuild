"""Structured models for the lint and format layer."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledModel, CompiledObjectKey, ExpansionSpan
from sqlbuild.compiler.scopes.types import DeclarationKind
from sqlbuild.lint.constants import (
    DEFAULT_MAX_LITERAL_LENGTH,
    DEFAULT_MAX_RANKING_ORDER_BY,
    VIOLATION_SEVERITY_FAULT,
    VIOLATION_SEVERITY_WARNING,
)
from sqlbuild.lint.exceptions import ProjectCompileError
from sqlbuild.lint.types import (
    DiagnosticIdentity,
    LintSeverity,
    NativeLintPreparationRequest,
    RuleFixStatus,
)


@dataclass(frozen=True)
class HeaderSpan:
    """A located DSL header region inside one file."""

    kind: str
    start: int
    end: int


@dataclass(frozen=True)
class LintFileRole:
    """Path-derived classification of one lint input, derived once per file."""

    declaration_kind: DeclarationKind | None = None
    in_project: bool = False
    in_hook_directory: bool = False


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
    dependency_relations: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class PendingLintBody:
    """One expanded authored body awaiting its native lexical preparation."""

    file_path: Path
    body_start: int
    body_end: int
    expansion_input: str
    expanded: str
    expansion_passes: tuple[tuple[ExpansionSpan, ...], ...]
    pre_expansion_sites: tuple[InterpolationSite, ...]
    external_identifiers: tuple[str, ...]
    allows_ceremonial_select: bool
    allows_dynamic_output_star: bool
    allows_empty_fixture_star: bool
    request: NativeLintPreparationRequest


@dataclass(frozen=True)
class ExpandedLintFile:
    """The expanded bodies of one file, up to the first body that could not be expanded."""

    file_path: Path
    bodies: tuple[PendingLintBody, ...]
    failure: ProjectCompileError | None


@dataclass(frozen=True)
class PreparedLintFiles:
    """Lint bodies of every expandable file, and why the skipped files could not expand."""

    bodies: tuple[LintBody, ...]
    unexpandable: dict[Path, str]


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
    status: RuleFixStatus
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
    max_description_lines: int = 10
    line_width: int = 100
    dialect: str = "generic"
    enabled_native_rules: tuple[str, ...] | None = None
    ignored_native_rules: tuple[str, ...] = ()
    header_rules_enabled: bool = True
    max_literal_length: int = DEFAULT_MAX_LITERAL_LENGTH
    max_ranking_order_by: int = DEFAULT_MAX_RANKING_ORDER_BY
    relation_keys: Mapping[str, tuple[tuple[str, ...], ...]] = field(
        default_factory=dict, compare=False
    )


@dataclass(frozen=True)
class LintRunResult:
    """Aggregated outcome of one lint or format run."""

    files_checked: int
    violations: tuple[LintViolation, ...]
    formatted_files: tuple[Path, ...]
    format_changes: tuple[FormatChange, ...] = ()
    rule_fixes: tuple[RuleFixResult, ...] = ()
    source_texts: Mapping[Path, str] = field(default_factory=dict, repr=False, compare=False)
    unexpandable: Mapping[Path, str] = field(default_factory=dict)

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
class CompileFacts:
    """Per-model outputs and per-owner diagnostics of one compilation."""

    models: dict[CompiledObjectKey, CompiledModel]
    model_paths: dict[CompiledObjectKey, Path]
    diagnostics: dict[Path, Counter[DiagnosticIdentity]]


@dataclass(frozen=True)
class FixVerdict:
    """Edited files that fail verification, and whether any change is unattributable."""

    failing: dict[Path, str]
    unattributed: bool

    @property
    def verified(self) -> bool:
        return not self.failing and not self.unattributed
