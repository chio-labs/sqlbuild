"""Structured kata configuration, rule, and evaluation models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.kata_engine.types import KataCheck, RuleOptionValue


@dataclass(frozen=True)
class RuleOption[T]:
    """One typed configuration option declared by a kata rule."""

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
class KataRule:
    """Immutable metadata and implementation for one kata rule."""

    code: str
    family: str
    slug: str
    message: str
    remediation: str
    check: KataCheck
    options: tuple[RuleOption[object], ...] = ()
    enabled_by_default: bool = False
    custom: bool = False
    source: str | None = None
    project_wide: bool = False
    guidance: RuleGuidance | None = None


@dataclass(frozen=True)
class KataFault:
    """One deterministic kata policy violation."""

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
class KataCacheConfig:
    enabled: bool = True
    require_cacheable: bool = False


@dataclass(frozen=True)
class SqlTestPolicyConfig:
    pipeline_directory: str = "pipelines"


@dataclass(frozen=True)
class KataConfig:
    select: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    thresholds: dict[str, int] = field(default_factory=dict)
    threshold_overrides: tuple[ThresholdOverride, ...] = ()
    rule_options: dict[str, dict[str, RuleOptionValue]] = field(default_factory=dict)
    rule_exceptions: tuple[RuleExemption, ...] = ()
    rule_ignores: tuple[RuleIgnore, ...] = ()
    select_star_allow: tuple[SelectStarAllow, ...] = ()
    rule_paths: tuple[str, ...] = ()
    rule_modules: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    approved_source_tokens: tuple[str, ...] = ()
    retired_source_tokens: dict[str, str] = field(default_factory=dict)
    cte_name_whitelist: tuple[str, ...] = ()
    cte_name_denylist: tuple[str, ...] = ()
    sql_tests: SqlTestPolicyConfig = field(default_factory=SqlTestPolicyConfig)
    cache: KataCacheConfig = field(default_factory=KataCacheConfig)


@dataclass(frozen=True)
class KataResult:
    faults: tuple[KataFault, ...]
    evaluated_models: int
    cache_hits: int = 0
    cache_misses: int = 0


@dataclass(frozen=True)
class ResolvedRuleset:
    catalogue: tuple[KataRule, ...]
    rules: tuple[KataRule, ...]
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
    expected_fault_count: int
    path: str = "models/mart/example__mart__result.sql"
    files: tuple[RuleFile, ...] = ()
    config: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleResult:
    faults: tuple[KataFault, ...]

    @property
    def fault_count(self) -> int:
        return len(self.faults)
