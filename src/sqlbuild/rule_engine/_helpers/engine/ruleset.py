"""Single rules catalogue and active-ruleset resolution."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.rule_engine._helpers.engine.catalogue import build_catalogue, select_rules
from sqlbuild.rule_engine._helpers.engine.config import resolve_rule_ignore_selectors
from sqlbuild.rule_engine._helpers.engine.custom_rule_evidence import (
    custom_rule_implementation_fingerprint,
)
from sqlbuild.rule_engine._helpers.engine.hermeticity import verify_custom_rules
from sqlbuild.rule_engine._helpers.engine.native import evaluate_native
from sqlbuild.rule_engine.models import ResolvedRuleset, Rule, RulesConfig, RulesResult


def evaluate_project(
    *, project: CompiledProject, config: RulesConfig, project_dir: Path, dialect: str = "generic"
) -> RulesResult:
    """Evaluate selected rules through one native project boundary."""

    effective_config: RulesConfig = resolve_rule_ignore_selectors(config=config, project=project)
    catalogue: tuple[Rule, ...] = build_catalogue(
        config=effective_config,
        project_dir=project_dir,
        include_custom=_config_selects_custom(effective_config),
    )
    if any(rule.custom for rule in catalogue):
        selected: tuple[Rule, ...] = select_rules(
            catalogue=catalogue, config=effective_config, project_dir=project_dir
        )
        verify_custom_rules(rules=selected, project_dir=project_dir)
    return evaluate_native(
        project=project,
        config=effective_config,
        project_dir=project_dir,
        catalogue=catalogue,
        dialect=dialect,
    )


def resolve_ruleset(*, config: RulesConfig, project_dir: Path) -> ResolvedRuleset:
    """Resolve one immutable ruleset for evaluation, inspection, caching, and skills."""

    catalogue: tuple[Rule, ...] = build_catalogue(
        config=config,
        project_dir=project_dir,
        include_custom=_config_selects_custom(config),
    )
    rules: tuple[Rule, ...] = select_rules(
        catalogue=catalogue, config=config, project_dir=project_dir
    )
    custom_selected: bool = any(rule.custom for rule in rules)
    cacheable: bool = True
    if custom_selected:
        verify_custom_rules(rules=rules, project_dir=project_dir)
    payload: list[dict[str, object]] = []
    for rule in rules:
        source_hash: str | None = None
        if rule.source is not None:
            source_hash = hashlib.sha256(Path(rule.source).read_bytes()).hexdigest()
        implementation_hash: str = custom_rule_implementation_fingerprint(
            rule=rule, project_dir=project_dir
        )
        payload.append(
            {
                "code": rule.code,
                "family": rule.family,
                "slug": rule.slug,
                "message": rule.message,
                "remediation": rule.remediation,
                "options": config.rule_options.get(rule.code, {}),
                "source_hash": source_hash,
                "implementation_hash": implementation_hash,
            }
        )
    rules_payload: dict[str, object] = {
        "engine": _engine_fingerprint(),
        "rules": payload,
        "thresholds": config.thresholds,
        "threshold_overrides": config.threshold_overrides,
        "select_star_allow": config.select_star_allow,
        "domains": config.domains,
        "approved_source_tokens": config.approved_source_tokens,
        "retired_source_tokens": config.retired_source_tokens,
        "sql_tests": config.sql_tests,
        "layout": config.layout,
        "exceptions": config.rule_exceptions,
        "ignores": config.rule_ignores,
    }
    fingerprint: str = hashlib.sha256(
        json.dumps(rules_payload, sort_keys=True, default=str).encode()
    ).hexdigest()
    return ResolvedRuleset(
        catalogue=catalogue,
        rules=rules,
        fingerprint=fingerprint,
        cacheable=cacheable,
    )


def _engine_fingerprint() -> str:
    digest: Any = hashlib.sha256()
    engine_root: Path = Path(__file__).parents[2]
    for path in sorted(engine_root.rglob("*.py")):
        digest.update(path.relative_to(engine_root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _config_selects_custom(config: RulesConfig) -> bool:
    ignored_selectors: list[str] = []
    for entry in config.rule_ignores:
        ignored_selectors.extend(entry.rules)
    selectors: tuple[str, ...] = (
        *config.select,
        *config.ignore,
        *config.rule_options,
        *(entry.rule for entry in config.rule_exceptions),
        *ignored_selectors,
    )
    return any(selector.startswith("XSQBR") for selector in selectors)
