"""Native-owned strict kata configuration loading."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from sqlbuild.kata_engine._helpers.engine.native import load_native_config
from sqlbuild.kata_engine.models import (
    KataCacheConfig,
    KataConfig,
    RuleExemption,
    RuleIgnore,
    SelectStarAllow,
    ThresholdOverride,
)
from sqlbuild.kata_engine.types import RuleOptionValue


def load_kata_config(project_dir: Path) -> KataConfig:
    """Load configuration validated and normalized by the native engine."""

    payload: dict[str, object] = load_native_config(project_dir)
    return KataConfig(
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
            )
            for item in _tables(payload.get("rule_ignores"))
        ),
        select_star_allow=tuple(
            SelectStarAllow(paths=_strings(item.get("paths")), reason=str(item["reason"]))
            for item in _tables(payload.get("select_star_allow"))
        ),
        rule_paths=_strings(payload.get("rule_paths")),
        rule_modules=_strings(payload.get("rule_modules")),
        domains=_strings(payload.get("domains")),
        approved_source_tokens=_strings(payload.get("approved_source_tokens")),
        retired_source_tokens=_string_mapping(payload.get("retired_source_tokens")),
        cte_name_whitelist=_strings(payload.get("cte_name_whitelist")),
        cte_name_denylist=_strings(payload.get("cte_name_denylist")),
        cache=_cache(payload.get("cache")),
    )


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


def _cache(value: object) -> KataCacheConfig:
    table: dict[str, object] = (
        {str(key): item for key, item in value.items()} if isinstance(value, dict) else {}
    )
    return KataCacheConfig(
        enabled=bool(table.get("enabled", True)),
        require_cacheable=bool(table.get("require_cacheable", False)),
    )
