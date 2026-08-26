"""Single kata catalogue and active-ruleset resolution."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.kata_engine._helpers.engine.catalogue import build_catalogue, select_rules
from sqlbuild.kata_engine._helpers.engine.custom_rule_evidence import (
    custom_rule_implementation_fingerprint,
)
from sqlbuild.kata_engine._helpers.engine.hermeticity import verify_custom_rules
from sqlbuild.kata_engine._helpers.engine.native import evaluate_native
from sqlbuild.kata_engine.models import KataConfig, KataResult, KataRule, ResolvedRuleset


def evaluate_project(
    *, project: CompiledProject, config: KataConfig, project_dir: Path
) -> KataResult:
    """Evaluate selected rules through one native project boundary."""

    catalogue: tuple[KataRule, ...] = build_catalogue(config=config, project_dir=project_dir)
    if config.cache.require_cacheable and any(rule.custom for rule in catalogue):
        selected: tuple[KataRule, ...] = select_rules(
            catalogue=catalogue, config=config, project_dir=project_dir
        )
        verify_custom_rules(rules=selected, project_dir=project_dir)
    return evaluate_native(
        project=project,
        config=config,
        project_dir=project_dir,
        catalogue=catalogue,
    )


def resolve_ruleset(*, config: KataConfig, project_dir: Path) -> ResolvedRuleset:
    """Resolve one immutable ruleset for evaluation, inspection, caching, and skills."""

    catalogue: tuple[KataRule, ...] = build_catalogue(config=config, project_dir=project_dir)
    rules: tuple[KataRule, ...] = select_rules(
        catalogue=catalogue, config=config, project_dir=project_dir
    )
    custom_selected: bool = any(rule.custom for rule in rules)
    cacheable: bool = not custom_selected or config.cache.require_cacheable
    if custom_selected and config.cache.require_cacheable:
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
    policy: dict[str, object] = {
        "engine": _engine_fingerprint(),
        "rules": payload,
        "thresholds": config.thresholds,
        "threshold_overrides": config.threshold_overrides,
        "select_star_allow": config.select_star_allow,
        "domains": config.domains,
        "approved_source_tokens": config.approved_source_tokens,
        "retired_source_tokens": config.retired_source_tokens,
        "cte_name_whitelist": config.cte_name_whitelist,
        "cte_name_denylist": config.cte_name_denylist,
        "sql_tests": config.sql_tests,
        "exceptions": config.rule_exceptions,
        "ignores": config.rule_ignores,
    }
    fingerprint: str = hashlib.sha256(
        json.dumps(policy, sort_keys=True, default=str).encode()
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
