"""Strict kata configuration loading from sqlbuild_project.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import cast

from sqlbuild.compiler.discovery.constants import PROJECT_CONFIG_FILENAME
from sqlbuild.kata_engine.constants import KATA_THRESHOLD_DEFAULTS
from sqlbuild.kata_engine.exceptions import KataError
from sqlbuild.kata_engine.models import (
    KataCacheConfig,
    KataConfig,
    RuleExemption,
    RuleIgnore,
    SelectStarAllow,
)
from sqlbuild.kata_engine.types import RuleOptionValue

_KNOWN_KEYS: frozenset[str] = frozenset(
    {
        "select",
        "ignore",
        "thresholds",
        "rule_options",
        "rule_exceptions",
        "rule_ignores",
        "select_star_allow",
        "rule_paths",
        "rule_modules",
        "domains",
        "approved_source_tokens",
        "retired_source_tokens",
        "cte_name_whitelist",
        "cte_name_denylist",
        "cache",
    }
)
_TABLE_KEYS: dict[str, frozenset[str]] = {
    "kata.rule_exceptions": frozenset({"path", "reason", "rule"}),
    "kata.rule_ignores": frozenset({"paths", "reason", "rules"}),
    "kata.select_star_allow": frozenset({"paths", "reason"}),
}


def load_kata_config(project_dir: Path) -> KataConfig:
    """Load and validate the optional kata table."""

    path: Path = project_dir / PROJECT_CONFIG_FILENAME
    try:
        payload: object = tomllib.loads(path.read_text(encoding="utf-8")).get("kata", {})
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise KataError(f"could not load kata config from {path}: {error}") from error
    table: dict[str, object] = _mapping(value=payload, label="kata")
    unknown: set[str] = set(table) - _KNOWN_KEYS
    if unknown:
        raise KataError(f"unknown kata config keys: {', '.join(sorted(unknown))}")
    return KataConfig(
        select=_strings(value=table.get("select"), label="kata.select"),
        ignore=_strings(value=table.get("ignore"), label="kata.ignore"),
        thresholds=_integers(value=table.get("thresholds"), label="kata.thresholds"),
        rule_options=_rule_options(table.get("rule_options")),
        rule_exceptions=tuple(
            RuleExemption(
                rule=_required_string(table=item, key="rule", label="kata.rule_exceptions"),
                path=_required_string(table=item, key="path", label="kata.rule_exceptions"),
                reason=_required_string(table=item, key="reason", label="kata.rule_exceptions"),
            )
            for item in _tables(value=table.get("rule_exceptions"), label="kata.rule_exceptions")
        ),
        rule_ignores=tuple(
            RuleIgnore(
                rules=_strings(
                    value=item.get("rules"), label="kata.rule_ignores.rules", required=True
                ),
                paths=_strings(
                    value=item.get("paths"), label="kata.rule_ignores.paths", required=True
                ),
                reason=_required_string(table=item, key="reason", label="kata.rule_ignores"),
            )
            for item in _tables(value=table.get("rule_ignores"), label="kata.rule_ignores")
        ),
        select_star_allow=tuple(
            SelectStarAllow(
                paths=_strings(
                    value=item.get("paths"), label="kata.select_star_allow.paths", required=True
                ),
                reason=_required_string(table=item, key="reason", label="kata.select_star_allow"),
            )
            for item in _tables(
                value=table.get("select_star_allow"), label="kata.select_star_allow"
            )
        ),
        rule_paths=_strings(value=table.get("rule_paths"), label="kata.rule_paths"),
        rule_modules=_strings(value=table.get("rule_modules"), label="kata.rule_modules"),
        domains=_strings(value=table.get("domains"), label="kata.domains"),
        approved_source_tokens=_strings(
            value=table.get("approved_source_tokens"), label="kata.approved_source_tokens"
        ),
        retired_source_tokens=_string_mapping(
            value=table.get("retired_source_tokens"), label="kata.retired_source_tokens"
        ),
        cte_name_whitelist=_strings(
            value=table.get("cte_name_whitelist"), label="kata.cte_name_whitelist"
        ),
        cte_name_denylist=_strings(
            value=table.get("cte_name_denylist"), label="kata.cte_name_denylist"
        ),
        cache=_cache(table.get("cache")),
    )


def _mapping(*, value: object, label: str) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise KataError(f"{label} must be a table")
    return {str(key): item for key, item in value.items()}


def _tables(*, value: object, label: str) -> tuple[dict[str, object], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise KataError(f"{label} must be an array of tables")
    tables: tuple[dict[str, object], ...] = tuple(
        _mapping(value=item, label=label) for item in value
    )
    allowed: frozenset[str] | None = _TABLE_KEYS.get(label)
    if allowed is not None:
        for table in tables:
            unknown: set[str] = set(table) - allowed
            if unknown:
                raise KataError(f"unknown {label} keys: {', '.join(sorted(unknown))}")
    return tables


def _strings(*, value: object, label: str, required: bool = False) -> tuple[str, ...]:
    if value is None and not required:
        return ()
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise KataError(f"{label} must be a non-empty list of strings")
    return tuple(cast(list[str], value))


def _required_string(*, table: dict[str, object], key: str, label: str) -> str:
    value: object = table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise KataError(f"{label}.{key} must be a non-empty string")
    return value


def _integers(*, value: object, label: str) -> dict[str, int]:
    table: dict[str, object] = _mapping(value=value, label=label)
    if any(
        not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in table.values()
    ):
        raise KataError(f"{label} values must be non-negative integers")
    unknown: set[str] = set(table) - set(KATA_THRESHOLD_DEFAULTS)
    if unknown:
        raise KataError(f"unknown kata thresholds: {', '.join(sorted(unknown))}")
    return {key: cast(int, item) for key, item in table.items()}


def _string_mapping(*, value: object, label: str) -> dict[str, str]:
    table: dict[str, object] = _mapping(value=value, label=label)
    if any(not isinstance(item, str) or not item.strip() for item in table.values()):
        raise KataError(f"{label} values must be non-empty strings")
    return {key: str(item) for key, item in table.items()}


def _rule_options(value: object) -> dict[str, dict[str, RuleOptionValue]]:
    result: dict[str, dict[str, RuleOptionValue]] = {}
    for code, raw_options in _mapping(value=value, label="kata.rule_options").items():
        options: dict[str, object] = _mapping(value=raw_options, label=f"kata.rule_options.{code}")
        normalized: dict[str, RuleOptionValue] = {}
        for name, item in options.items():
            if isinstance(item, (bool, int, str)):
                normalized[name] = item
            elif isinstance(item, list) and all(isinstance(entry, str) for entry in item):
                normalized[name] = tuple(cast(list[str], item))
            elif isinstance(item, list) and all(
                isinstance(entry, int) and not isinstance(entry, bool) for entry in item
            ):
                normalized[name] = tuple(cast(list[int], item))
            else:
                raise KataError(f"kata.rule_options.{code}.{name} has an unsupported value")
        result[code] = normalized
    return result


def _cache(value: object) -> KataCacheConfig:
    table: dict[str, object] = _mapping(value=value, label="kata.cache")
    unknown: set[str] = set(table) - {"enabled", "require_cacheable"}
    if unknown:
        raise KataError(f"unknown kata.cache keys: {', '.join(sorted(unknown))}")
    enabled: object = table.get("enabled", True)
    require_cacheable: object = table.get("require_cacheable", False)
    if not isinstance(enabled, bool) or not isinstance(require_cacheable, bool):
        raise KataError("kata.cache values must be booleans")
    return KataCacheConfig(enabled=enabled, require_cacheable=require_cacheable)
