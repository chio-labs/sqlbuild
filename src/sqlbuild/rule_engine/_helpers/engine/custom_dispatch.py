"""Dispatch custom rules to their worker thread beside native built-in rule evaluation."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from functools import partial
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.frontier.main.compiled_code_identity import compiled_code_identity
from sqlbuild.rule_engine._helpers.engine.custom_rules import evaluate_custom_rules_cached
from sqlbuild.rule_engine._helpers.engine.native import (
    custom_rule_payloads,
    finalize_native_findings,
    rule_selected,
    selected_codes,
)
from sqlbuild.rule_engine._helpers.run.native_rows import (
    build_rules_request,
    evaluate_rules_request,
)
from sqlbuild.rule_engine.constants import TYPE_PROOF_RULE_CODES
from sqlbuild.rule_engine.models import (
    CustomRulesOutcome,
    Finding,
    NativeRulesEvaluation,
    Rule,
    RulesConfig,
    RulesResult,
)


def evaluate_native(
    *,
    project: CompiledProjectView,
    config: RulesConfig,
    project_dir: Path,
    catalogue: tuple[Rule, ...],
    dialect: str = "generic",
    initial_findings: tuple[Finding, ...] = (),
    defer_suppressions: bool = False,
    verify_determinism: bool = False,
    custom_payloads: list[dict[str, object]] | None = None,
    custom_outcome: Future[CustomRulesOutcome] | None = None,
) -> RulesResult:
    """Evaluate built-in rules natively while custom rules run incrementally beside them."""

    payloads: list[dict[str, object]] = (
        custom_rule_payloads(catalogue=catalogue, project_dir=project_dir)
        if custom_payloads is None
        else custom_payloads
    )
    return _evaluate_native_rows(
        project=project,
        config=config,
        project_dir=project_dir,
        dialect=dialect,
        initial_findings=initial_findings,
        defer_suppressions=defer_suppressions,
        custom_payloads=payloads,
        start_custom=(
            (lambda **_: custom_outcome)
            if custom_payloads is not None
            else partial(
                start_custom_rules,
                project=project,
                config=config,
                project_dir=project_dir,
                catalogue=catalogue,
                custom_payloads=payloads,
                dialect=dialect,
                verify_determinism=verify_determinism,
            )
        ),
    )


def _evaluate_native_rows(
    *,
    project: CompiledProjectView,
    config: RulesConfig,
    project_dir: Path,
    dialect: str,
    initial_findings: tuple[Finding, ...],
    defer_suppressions: bool,
    custom_payloads: list[dict[str, object]],
    start_custom: Callable[..., Future[CustomRulesOutcome] | None],
) -> RulesResult:
    request: _native.NativeRulesRequest = build_rules_request(
        project=project,
        config=config,
        project_dir=project_dir,
        dialect=dialect,
        initial_findings=initial_findings,
        custom_payloads=custom_payloads,
        include_type_proof=any(
            rule_selected(config=config, code=code) for code in TYPE_PROOF_RULE_CODES
        ),
    )
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="sqlbuild-custom-rules") as pool:
        custom_future: Future[CustomRulesOutcome] | None = start_custom(executor=pool)
        native: NativeRulesEvaluation = evaluate_rules_request(request)
        del request
        custom: CustomRulesOutcome = (
            CustomRulesOutcome(findings=(), cache_hits=0, cache_misses=0, custom_ms=0)
            if custom_future is None
            else custom_future.result()
        )
    findings: tuple[Finding, ...] = (
        *native.findings,
        *custom.findings,
    )
    if not defer_suppressions:
        findings = finalize_native_findings(
            config=config,
            project_dir=project_dir,
            evaluated_codes=native.selected_codes,
            findings=findings,
        )
    return RulesResult(
        findings=findings,
        evaluated_models=native.evaluated_models,
        cache_hits=(native.cache_hits + native.cache_misses if native.reused else native.cache_hits)
        + custom.cache_hits,
        cache_misses=(0 if native.reused else native.cache_misses) + custom.cache_misses,
        built_in_ms=0 if native.reused else native.built_in_ms,
        custom_ms=custom.custom_ms,
        custom_cpu_ms=custom.custom_cpu_ms,
    )


def start_custom_rules(
    *,
    executor: Executor,
    project: CompiledProjectView,
    config: RulesConfig,
    project_dir: Path,
    catalogue: tuple[Rule, ...],
    custom_payloads: list[dict[str, object]],
    dialect: str,
    verify_determinism: bool = False,
) -> Future[CustomRulesOutcome] | None:
    """Submit selected custom rules after digesting installed code here, clear of GIL contention."""

    custom_rules: tuple[Rule, ...] = _selected_custom_rules(
        config=config, catalogue=catalogue, custom_payloads=custom_payloads
    )
    if not custom_rules:
        return None
    if config.cache.enabled:
        _ = compiled_code_identity()
    return executor.submit(
        evaluate_custom_rules_cached,
        project=project,
        config=config,
        project_dir=project_dir.resolve(),
        rules=custom_rules,
        dialect=dialect,
        verify_determinism=verify_determinism,
        implementation_fingerprints={
            str(payload["code"]): str(payload["implementation_fingerprint"])
            for payload in custom_payloads
        },
    )


def _selected_custom_rules(
    *,
    config: RulesConfig,
    catalogue: tuple[Rule, ...],
    custom_payloads: list[dict[str, object]],
) -> tuple[Rule, ...]:
    if not custom_payloads:
        return ()
    selected: frozenset[str] = frozenset(
        selected_codes(config=config, custom_payloads=custom_payloads)
    )
    return tuple(rule for rule in catalogue if rule.custom and rule.code in selected)
