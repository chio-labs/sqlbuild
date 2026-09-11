"""Native-owned strict rules configuration loading."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.planner.main.selection.scope import build_planner_scope
from sqlbuild.compiler.planner.models import PlannerScope
from sqlbuild.rule_engine._helpers.engine.native import load_native_config
from sqlbuild.rule_engine.exceptions import RulesError
from sqlbuild.rule_engine.models import (
    LayoutConfig,
    RuleExemption,
    RuleIgnore,
    RulesCacheConfig,
    RulesConfig,
    SelectStarAllow,
    SqlTestRulesConfig,
    ThresholdOverride,
)
from sqlbuild.rule_engine.types import RuleOptionValue


def load_rules_config(project_dir: Path) -> RulesConfig:
    """Load configuration validated and normalized by the native engine."""

    payload: dict[str, object] = load_native_config(project_dir)
    return RulesConfig(
        select=_strings(payload.get("select")),
        ignore=_strings(payload.get("ignore")),
        thresholds=_integers(payload.get("thresholds")),
        threshold_overrides=tuple(
            ThresholdOverride(
                paths=_strings(item.get("paths")),
                thresholds=_integers(item.get("thresholds")),
                reason=str(item["reason"]),
            )
            for item in _tables(payload.get("threshold_overrides"))
        ),
        rule_options=_rule_options(payload.get("rule_options")),
        rule_exceptions=tuple(
            RuleExemption(
                rule=str(item["rule"]), path=str(item["path"]), reason=str(item["reason"])
            )
            for item in _tables(payload.get("rule_exceptions"))
        ),
        rule_ignores=tuple(
            RuleIgnore(
                rules=_strings(item.get("rules")),
                paths=_strings(item.get("paths")),
                reason=str(item["reason"]),
                selectors=_strings(item.get("selectors")),
            )
            for item in _tables(payload.get("rule_ignores"))
        ),
        select_star_allow=tuple(
            SelectStarAllow(paths=_strings(item.get("paths")), reason=str(item["reason"]))
            for item in _tables(payload.get("select_star_allow"))
        ),
        domains=_strings(payload.get("domains")),
        approved_source_tokens=_strings(payload.get("approved_source_tokens")),
        retired_source_tokens=_string_mapping(payload.get("retired_source_tokens")),
        sql_tests=_sql_tests(payload.get("sql_tests")),
        layout=_layout(payload.get("layout")),
        cache=_cache(payload.get("cache")),
    )


def resolve_rule_ignore_selectors(*, config: RulesConfig, project: CompiledProject) -> RulesConfig:
    """Resolve configured resource selectors into deterministic finding paths."""
    if not any(ignore.selectors for ignore in config.rule_ignores):
        return config
    path_by_key: dict[CompiledObjectKey, Path] = _resource_paths(project=project)
    resolved: list[RuleIgnore] = []
    for ignore in config.rule_ignores:
        if not ignore.selectors:
            resolved.append(ignore)
            continue
        scope: PlannerScope = build_planner_scope(project=project, select=ignore.selectors)
        selector_paths: set[str] = {
            path_by_key[key].as_posix() for key in scope.selected_keys if key in path_by_key
        }
        if not selector_paths:
            joined: str = ", ".join(ignore.selectors)
            raise RulesError(f"rule ignore selectors resolve no resources with paths: {joined}")
        resolved.append(
            replace(
                ignore,
                paths=tuple(sorted({*ignore.paths, *selector_paths})),
                selectors=(),
            )
        )
    return replace(config, rule_ignores=tuple(resolved))


def _resource_paths(*, project: CompiledProject) -> dict[CompiledObjectKey, Path]:
    paths: dict[CompiledObjectKey, Path] = {
        model.key: model.relative_path for model in project.models
    }
    paths.update({function.key: function.relative_path for function in project.functions})
    paths.update({seed.key: seed.seed_file.relative_path for seed in project.seeds})
    paths.update({source.key: source.source_file.relative_path for source in project.sources})
    return paths


def _strings(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in value) if isinstance(value, list) else ()


def _tables(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        return ()
    tables: list[dict[str, object]] = []
    for table in value:
        if isinstance(table, dict):
            tables.append({str(key): item for key, item in table.items()})
    return tuple(tables)


def _integers(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items() if isinstance(item, int)}


def _string_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _rule_options(value: object) -> dict[str, dict[str, RuleOptionValue]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, RuleOptionValue]] = {}
    for code, raw_options in value.items():
        if not isinstance(raw_options, dict):
            continue
        options: dict[str, RuleOptionValue] = {}
        for name, item in raw_options.items():
            if isinstance(item, list):
                options[str(name)] = cast("RuleOptionValue", tuple(item))
            elif isinstance(item, (bool, int, str)):
                options[str(name)] = item
        result[str(code)] = options
    return result


def _cache(value: object) -> RulesCacheConfig:
    table: dict[str, object] = (
        {str(key): item for key, item in value.items()} if isinstance(value, dict) else {}
    )
    return RulesCacheConfig(enabled=bool(table.get("enabled", True)))


def _sql_tests(value: object) -> SqlTestRulesConfig:
    table: dict[str, object] = (
        {str(key): item for key, item in value.items()} if isinstance(value, dict) else {}
    )
    return SqlTestRulesConfig(pipeline_directory=str(table.get("pipeline_directory", "pipelines")))


def _layout(value: object) -> LayoutConfig:
    table: dict[str, object] = (
        {str(key): item for key, item in value.items()} if isinstance(value, dict) else {}
    )
    levels: tuple[str, ...] = _strings(table.get("levels"))
    return LayoutConfig(
        levels=levels or LayoutConfig().levels,
        domain_roots=_strings(table.get("domain_roots")),
    )
