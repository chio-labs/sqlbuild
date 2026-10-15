"""Incremental custom-rule evaluation keyed on the compiler facts each invocation read."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import sqlbuild._native as _native
from sqlbuild._native import (
    CustomRuleCache,
    compiled_project_record,
    custom_rule_identity,
    custom_rule_implementation_fingerprint,
    custom_rule_import_closure,
    rules_bulk_cache_path,
)
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.scopes.models import ScopeIndex
from sqlbuild.rule_engine._helpers.engine.fact_replay import full_fact_keys, is_tree_fact
from sqlbuild.rule_engine._helpers.host.custom_host_pool import run_custom_hosts
from sqlbuild.rule_engine.classes.fact_digests import FactDigests
from sqlbuild.rule_engine.classes.rule_context import RuleFactViews, build_rule_fact_views
from sqlbuild.rule_engine.constants import (
    CUSTOM_HOST_RUNTIME_VERSION,
    CUSTOM_RULES_CACHE_FILE,
)
from sqlbuild.rule_engine.exceptions import FactDigestError
from sqlbuild.rule_engine.models import CustomHostRun, CustomRulesOutcome, Rule, RulesConfig
from sqlbuild.rule_engine.types import CustomEvaluationRow, FactKey


def evaluate_custom_rules_cached(
    *,
    project: CompiledProjectView,
    config: RulesConfig,
    project_dir: Path,
    rules: tuple[Rule, ...],
    dialect: str,
    verify_determinism: bool = False,
    implementation_fingerprints: dict[str, str] | None = None,
) -> CustomRulesOutcome:
    """Reuse results whose recorded fact reads are unchanged and evaluate only the rest."""

    started: float = time.monotonic()
    started_cpu: float = _cpu_seconds()
    custom: tuple[Rule, ...] = tuple(sorted(rules, key=lambda rule: rule.code))
    if not custom:
        return CustomRulesOutcome(findings=(), cache_hits=0, cache_misses=0, custom_ms=0)
    facts_project: CompiledProjectView = host_project(project)
    enabled: bool = config.cache.enabled
    cache: CustomRuleCache = CustomRuleCache(
        path=(
            rules_bulk_cache_path(project_dir=project_dir, file_name=CUSTOM_RULES_CACHE_FILE)
            if enabled
            else None
        ),
        rules=[
            (
                rule.code,
                _rule_identity(
                    rule=rule,
                    config=config,
                    project_dir=project_dir,
                    dialect=dialect,
                    fingerprint=(implementation_fingerprints or {}).get(rule.code),
                )
                if enabled
                else None,
                None if rule.subject is None else rule.subject.value,
            )
            for rule in custom
        ],
        target_name=project.effective_target_name,
        models=[
            (model.relative_path.as_posix(), model.name, _materialization(model))
            for model in project.models
        ],
    )
    digests: FactDigests = FactDigests(
        views=_views_factory(project=facts_project, project_dir=project_dir, dialect=dialect)
    )
    plan: dict[str, list[str] | None] = cache.plan(
        digests=[
            _readset_digest(readset=readset, digests=digests)
            for readset in cache.pending_readsets()
        ]
    )
    if plan:
        run: CustomHostRun = run_custom_hosts(
            project=facts_project,
            config=config,
            project_dir=project_dir,
            dialect=dialect,
            rules=custom,
            model_paths=tuple(sorted(model.relative_path.as_posix() for model in project.models)),
            plan=plan,
            track_reads=enabled,
            verify_determinism=verify_determinism,
        )
        cache.record(evaluated=_evaluations(run=run, digests=digests, cacheable=enabled))
    return CustomRulesOutcome(
        findings=tuple(cache.findings()),
        cache_hits=cache.hits,
        cache_misses=cache.misses,
        custom_ms=_elapsed_ms(started),
        custom_cpu_ms=_cpu_ms(started_cpu),
    )


def _views_factory(
    *, project: CompiledProjectView, project_dir: Path, dialect: str
) -> Callable[[], RuleFactViews]:
    def build() -> RuleFactViews:
        return build_rule_fact_views(project=project, project_dir=project_dir, dialect=dialect)

    return build


def _materialization(model: Any) -> str | None:
    value: object = model.config.values.get("materialized")
    return value if isinstance(value, str) else None


def _rule_identity(
    *, rule: Rule, config: RulesConfig, project_dir: Path, dialect: str, fingerprint: str | None
) -> str:
    return custom_rule_identity(
        code_identity=_native.compiled_code_identity(),
        runtime_version=CUSTOM_HOST_RUNTIME_VERSION,
        code=rule.code,
        family=rule.family,
        slug=rule.slug,
        message=rule.message,
        remediation=rule.remediation,
        subject=None if rule.subject is None else rule.subject.value,
        implementation_fingerprint=fingerprint
        if fingerprint is not None
        else custom_rule_implementation_fingerprint(
            rule=rule,
            project_dir=project_dir,
            import_closure=custom_rule_import_closure(rule=rule, project_dir=project_dir),
        ),
        config=config,
        dialect=dialect,
        project_dir=str(project_dir.resolve()),
    )


def _readset_digest(*, readset: tuple[FactKey, ...], digests: FactDigests) -> str | None:
    try:
        return digests.combined(readset)
    except FactDigestError:
        return None


def host_project(project: CompiledProjectView) -> CompiledProject:
    """Drop project state no Rule fact reads, before digests and host payloads use it."""

    return replace(
        compiled_project_record(project, include_sql_expansions=False),
        binding_catalog=None,
        sql_expansions={},
        loaded_macros={},
        loader_functions=(),
        hook_functions=(),
        materialization_files=(),
        external_sql_reference_resolver=None,
        sql_scenarios=(),
        sql_hook_files=(),
        diagnostics=(),
        unmatched_literal_sql_relations=(),
        scope_index=ScopeIndex(),
    )


def _evaluations(
    *, run: CustomHostRun, digests: FactDigests, cacheable: bool
) -> list[CustomEvaluationRow]:
    """Each evaluated invocation with its read set and its digest when it may be cached."""

    full_keys: tuple[FactKey, ...] | None = None
    combined: dict[tuple[FactKey, ...], str | None] = {}
    rows: list[CustomEvaluationRow] = []
    for (code, subject), result in run.evaluated.items():
        stored: tuple[tuple[FactKey, ...], str | None] | None = None
        if cacheable and code not in run.uncacheable:
            reads: tuple[FactKey, ...] | None = result.reads
            if reads is None:
                if full_keys is None:
                    full_keys = full_fact_keys(digests.views)
                reads = (*run.untracked_reads.get(code, ()), *full_keys)
            readset: tuple[FactKey, ...] = tuple(sorted(set(reads)))
            if readset not in combined:
                combined[readset] = _observed_digest(
                    readset=readset, observed=run.observed, digests=digests
                )
            stored = (readset, combined[readset])
        rows.append((code, subject, stored, list(result.findings)))
    return rows


def _observed_digest(
    *, readset: tuple[FactKey, ...], observed: dict[FactKey, str | None], digests: FactDigests
) -> str | None:
    """Digest a read set only when its filesystem facts still match what the rule observed."""

    try:
        for key in readset:
            if is_tree_fact(key) and key in observed and observed[key] != digests.digest(key):
                return None
        return digests.combined(readset)
    except FactDigestError:
        return None


def _cpu_seconds() -> float:
    """This thread's CPU plus that of finished child processes, which run the rule hosts."""

    times: os.times_result = os.times()
    return time.thread_time() + times.children_user + times.children_system


def _cpu_ms(started: float) -> int:
    return int((_cpu_seconds() - started) * 1000)


def _elapsed_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)
