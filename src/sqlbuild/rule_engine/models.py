"""Structured rules configuration, rule, and evaluation models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlbuild.rule_engine.types import RuleCheck, RuleOptionValue, RuleSubject


@dataclass(frozen=True, slots=True)
class Model:
    """Stable identity and common metadata for one compiled SQL model."""

    name: str
    path: Path
    materialization: str | None


@dataclass(frozen=True, slots=True)
class Project:
    """Stable summary for one compiled project invocation."""

    model_count: int
    target_name: str | None


@dataclass(frozen=True, slots=True, order=True)
class ProjectPath:
    """One normalized project-relative file or directory."""

    value: str
    is_file: bool
    is_dir: bool

    @property
    def parts(self) -> tuple[str, ...]:
        return Path(self.value).parts

    @property
    def name(self) -> str:
        return Path(self.value).name

    @property
    def depth(self) -> int:
        return len(self.parts)


@dataclass(frozen=True, slots=True)
class SqlNode:
    """Stable source location for one common SQL structure fact."""

    kind: str
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class ModelSql:
    """Authored and compiler-expanded SQL documents for one model."""

    authored: Any
    expanded: Any


@dataclass(frozen=True, slots=True)
class RuleFactViews:
    """Views shared by every invocation in one custom-rule host evaluation."""

    project: Any
    sql: Any
    graph: Any
    columns: Any
    contracts: Any
    tests: Any
    audits: Any
    declarations: Any


@dataclass(frozen=True)
class RuleOption[T]:
    """One typed configuration option declared by a rule."""

    name: str
    value_type: type[T]
    default: T
    description: str
    choices: tuple[T, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    minimum_items: int | None = None
    item_type: type[object] | None = None

    @classmethod
    def boolean(cls, *, name: str, default: bool, description: str) -> RuleOption[bool]:
        return RuleOption(name=name, value_type=bool, default=default, description=description)

    @classmethod
    def integer(
        cls,
        *,
        name: str,
        default: int,
        description: str,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> RuleOption[int]:
        return RuleOption(
            name=name,
            value_type=int,
            default=default,
            description=description,
            minimum=minimum,
            maximum=maximum,
        )

    @classmethod
    def string(
        cls,
        *,
        name: str,
        default: str,
        description: str,
        choices: tuple[str, ...] = (),
    ) -> RuleOption[str]:
        return RuleOption(
            name=name,
            value_type=str,
            default=default,
            description=description,
            choices=choices,
        )

    @classmethod
    def string_list(
        cls,
        *,
        name: str,
        default: tuple[str, ...],
        description: str,
        minimum_items: int | None = None,
    ) -> RuleOption[tuple[str, ...]]:
        return RuleOption(
            name=name,
            value_type=tuple,
            default=default,
            description=description,
            minimum_items=minimum_items,
            item_type=str,
        )

    @classmethod
    def integer_list(
        cls,
        *,
        name: str,
        default: tuple[int, ...],
        description: str,
        minimum_items: int | None = None,
    ) -> RuleOption[tuple[int, ...]]:
        return RuleOption(
            name=name,
            value_type=tuple,
            default=default,
            description=description,
            minimum_items=minimum_items,
            item_type=int,
        )


@dataclass(frozen=True)
class RuleGuidance:
    """Structured authoring guidance shared by diagnostics and generated documentation."""

    good_example: str
    anti_tautology: str
    mutation_check: str


@dataclass(frozen=True)
class Rule:
    """Immutable metadata and implementation for one rule."""

    code: str
    family: str
    slug: str
    message: str
    remediation: str
    check: RuleCheck
    options: tuple[RuleOption[object], ...] = ()
    enabled_by_default: bool = False
    custom: bool = False
    source: str | None = None
    subject: RuleSubject | None = None
    subject_parameter: str | None = None
    context_parameter: str | None = None
    guidance: RuleGuidance | None = None

    @property
    def project_wide(self) -> bool:
        """Return whether this rule is invoked once for the compiled project."""

        return self.subject is RuleSubject.PROJECT


@dataclass(frozen=True)
class Finding:
    """One deterministic compiler rules violation."""

    code: str
    path: Path
    line: int
    column: int
    message: str
    remediation: str


@dataclass(frozen=True)
class RuleExemption:
    rule: str
    path: str
    reason: str


@dataclass(frozen=True)
class RuleIgnore:
    rules: tuple[str, ...]
    paths: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class SelectStarAllow:
    paths: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ThresholdOverride:
    paths: tuple[str, ...]
    thresholds: dict[str, int]
    reason: str


@dataclass(frozen=True)
class RulesCacheConfig:
    enabled: bool = True


@dataclass(frozen=True)
class SqlTestRulesConfig:
    pipeline_directory: str = "pipelines"


@dataclass(frozen=True)
class LayoutConfig:
    levels: tuple[str, ...] = (
        "staging",
        "intermediate/clean",
        "intermediate/enriched",
        "mart",
    )
    domain_roots: tuple[str, ...] = ()


@dataclass(frozen=True)
class RulesConfig:
    select: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    thresholds: dict[str, int] = field(default_factory=dict)
    threshold_overrides: tuple[ThresholdOverride, ...] = ()
    rule_options: dict[str, dict[str, RuleOptionValue]] = field(default_factory=dict)
    rule_exceptions: tuple[RuleExemption, ...] = ()
    rule_ignores: tuple[RuleIgnore, ...] = ()
    select_star_allow: tuple[SelectStarAllow, ...] = ()
    domains: tuple[str, ...] = ()
    approved_source_tokens: tuple[str, ...] = ()
    retired_source_tokens: dict[str, str] = field(default_factory=dict)
    sql_tests: SqlTestRulesConfig = field(default_factory=SqlTestRulesConfig)
    layout: LayoutConfig = field(default_factory=LayoutConfig)
    cache: RulesCacheConfig = field(default_factory=RulesCacheConfig)


@dataclass(frozen=True)
class RulesResult:
    findings: tuple[Finding, ...]
    evaluated_models: int
    cache_hits: int = 0
    cache_misses: int = 0
    built_in_ms: int = 0
    custom_ms: int = 0


@dataclass(frozen=True)
class RulesRunResult:
    """Unified findings and phase measurements for configured rules."""

    findings: tuple[Finding, ...]
    evaluated_models: int
    built_in_ms: int
    custom_ms: int
    cache_hits: int = 0
    cache_misses: int = 0


@dataclass(frozen=True)
class ResolvedRuleset:
    catalogue: tuple[Rule, ...]
    rules: tuple[Rule, ...]
    fingerprint: str
    cacheable: bool


@dataclass(frozen=True)
class ModelNameParts:
    domain: str
    layer: str
    entity: str
    source: str | None
    is_view: bool


@dataclass(frozen=True)
class RuleFile:
    path: str
    source: str


@dataclass(frozen=True)
class RuleCase:
    description: str
    source: str
    expected_finding_count: int
    path: str = "models/mart/example__mart__result.sql"
    files: tuple[RuleFile, ...] = ()
    config: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleResult:
    findings: tuple[Finding, ...]

    @property
    def finding_count(self) -> int:
        return len(self.findings)
