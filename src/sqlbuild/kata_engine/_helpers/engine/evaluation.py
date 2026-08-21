"""Kata project evaluation orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from sqlbuild.kata_engine._helpers.engine.cache import (
    decode_faults,
    encode_entry,
    load_cache,
    model_fingerprint,
    project_fingerprint,
    save_cache,
)
from sqlbuild.kata_engine._helpers.engine.ruleset import resolve_ruleset
from sqlbuild.kata_engine._helpers.engine.suppressions import (
    apply_suppressions,
    validate_exception_codes,
    validate_exceptions,
)
from sqlbuild.kata_engine.classes.rule_context import EvaluationRuleContext
from sqlbuild.kata_engine.exceptions import KataError
from sqlbuild.kata_engine.models import KataConfig, KataFault, KataResult, ResolvedRuleset


def evaluate_project(
    *, project: CompiledProject, config: KataConfig, project_dir: Path
) -> KataResult:
    """Evaluate selected rules with parsing, caching, and suppression."""

    ruleset: ResolvedRuleset = resolve_ruleset(config=config, project_dir=project_dir)
    validate_exception_codes(config=config, catalogue=ruleset.catalogue)
    if not ruleset.rules:
        validate_exceptions(config=config, faults=[], project_dir=project_dir)
        return KataResult(faults=(), evaluated_models=0)
    polyglot: Any | None = import_polyglot_sql()
    if polyglot is None:
        raise KataError("kata requires the bundled polyglot_sql package")
    faults: list[KataFault] = []
    evaluated_models: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_enabled: bool = config.cache.enabled and ruleset.cacheable
    cache_entries: dict[str, dict[str, object]] = (
        load_cache(project_dir=project_dir) if cache_enabled else {}
    )
    shared_project_fingerprint: str | None = (
        project_fingerprint(project=project, ruleset=ruleset, project_dir=project_dir)
        if cache_enabled
        else None
    )
    models: tuple[CompiledModel, ...] = tuple(
        sorted(project.models, key=lambda item: item.relative_path.as_posix())
    )
    for model_index, model in enumerate(models):
        fingerprint: str = (
            model_fingerprint(
                model=model,
                ruleset=ruleset,
                project_fingerprint=shared_project_fingerprint,
            )
            if cache_enabled
            else ""
        )
        cache_key: str = model.relative_path.as_posix()
        cached_faults: list[KataFault] | None = (
            decode_faults(
                entry=cache_entries.get(cache_key, {}),
                expected_fingerprint=fingerprint,
            )
            if cache_enabled
            else None
        )
        if cached_faults is not None:
            faults.extend(cached_faults)
            cache_hits += 1
            evaluated_models += 1
            continue
        cache_misses += 1
        try:
            ast: Any = polyglot.parse_one(model.query_sql, dialect="generic")
        except Exception as error:
            raise KataError(f"could not parse {model.relative_path} for kata: {error}") from error
        evaluated_models += 1
        model_faults: list[KataFault] = []
        for rule in ruleset.rules:
            if rule.project_wide and model_index != 0:
                continue
            ctx: EvaluationRuleContext = EvaluationRuleContext(
                model=model,
                ast=ast,
                rule=rule,
                config=config,
                project=project,
                project_dir=project_dir,
                selected_rules=ruleset.rules,
                is_project_anchor=model_index == 0,
            )
            try:
                model_faults.extend(rule.check(model=model, ctx=ctx))
            except Exception as error:
                raise KataError(
                    f"kata rule {rule.code} failed for {model.relative_path}: {error}"
                ) from error
        faults.extend(model_faults)
        if cache_enabled:
            cache_entries[cache_key] = encode_entry(
                fingerprint=fingerprint,
                faults=model_faults,
            )
    if cache_enabled:
        _ = save_cache(project_dir=project_dir, entries=cache_entries)
    visible: list[KataFault] = apply_suppressions(faults=faults, config=config)
    validate_exceptions(config=config, faults=faults, project_dir=project_dir)
    return KataResult(
        faults=tuple(
            sorted(
                visible, key=lambda item: (item.path.as_posix(), item.line, item.column, item.code)
            )
        ),
        evaluated_models=evaluated_models,
        cache_hits=cache_hits,
        cache_misses=cache_misses,
    )
