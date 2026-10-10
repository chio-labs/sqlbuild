"""Typed Python adapter for the private native rules engine."""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import asdict, replace
from functools import partial
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import (
    CompiledProject,
)
from sqlbuild.compiler.frontier.main.compiled_code_identity import compiled_code_identity
from sqlbuild.rule_engine._helpers.engine.custom_rule_evidence import (
    custom_rule_implementation_fingerprint,
    custom_rule_import_closure,
    custom_rule_test_evidence,
)
from sqlbuild.rule_engine._helpers.engine.custom_rules import evaluate_custom_rules_cached
from sqlbuild.rule_engine._helpers.run.native_rows import (
    build_rules_request,
    evaluate_rules_request,
    finalize_rules_rows,
)
from sqlbuild.rule_engine.constants import (
    RULES_NATIVE_API_VERSION,
    TYPE_PROOF_RULE_CODES,
)
from sqlbuild.rule_engine.exceptions import RulesError
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
    project: CompiledProject,
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
    project: CompiledProject,
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
            _rule_selected(config=config, code=code) for code in TYPE_PROOF_RULE_CODES
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
        *(decode_rule_finding(value) for value in custom.findings),
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
    project: CompiledProject,
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
        _selected_codes(config=config, custom_payloads=custom_payloads)
    )
    return tuple(rule for rule in catalogue if rule.custom and rule.code in selected)


def finalize_native_findings(
    *,
    config: RulesConfig,
    project_dir: Path,
    evaluated_codes: tuple[str, ...],
    findings: tuple[Finding, ...],
) -> tuple[Finding, ...]:
    """Apply exception policy once to completed SQL, native, and custom findings."""

    return _with_fixable(
        original=findings,
        finalized=finalize_rules_rows(
            config=config,
            project_dir=project_dir,
            evaluated_codes=evaluated_codes,
            findings=findings,
        ),
    )


def _with_fixable(
    *, original: tuple[Finding, ...], finalized: tuple[Finding, ...]
) -> tuple[Finding, ...]:
    fixable: frozenset[tuple[str, str, int, int, str]] = frozenset(
        _finding_identity(finding) for finding in original if finding.fixable
    )
    return tuple(
        replace(finding, fixable=True) if _finding_identity(finding) in fixable else finding
        for finding in finalized
    )


def _finding_identity(finding: Finding) -> tuple[str, str, int, int, str]:
    return (
        finding.code,
        finding.path.as_posix(),
        finding.line,
        finding.column,
        finding.message,
    )


def load_native_config(project_dir: Path) -> dict[str, object]:
    """Load strict rules TOML through the native configuration owner."""

    try:
        payload: object = json.loads(_native.load_config_json(str(project_dir.resolve())))
    except (ValueError, TypeError) as error:
        raise RulesError(str(error)) from error
    if not isinstance(payload, dict):
        raise RulesError("native rules engine returned invalid configuration")
    return {str(key): value for key, value in payload.items()}


def native_catalogue() -> tuple[dict[str, object], ...]:
    """Return native-owned built-in rule metadata."""

    try:
        payload: object = json.loads(_native.catalogue_json())
    except (ValueError, TypeError) as error:
        raise RulesError(str(error)) from error
    if not isinstance(payload, dict) or not isinstance(payload.get("rules"), list):
        raise RulesError("native rules engine returned an invalid catalogue")
    rules: list[object] = payload["rules"]
    if any(not isinstance(value, dict) for value in rules):
        raise RulesError("native rules engine returned invalid rule metadata")
    normalized: list[dict[str, object]] = []
    for value in rules:
        normalized.append({str(key): item for key, item in value.items()})
    return tuple(normalized)


def native_selected_codes(
    *,
    config: RulesConfig,
    catalogue: tuple[Rule, ...],
    project_dir: Path,
    custom_payloads: list[dict[str, object]] | None = None,
) -> tuple[str, ...]:
    """Resolve the active ruleset through the native Fensu adapter."""

    return _selected_codes(
        config=config,
        custom_payloads=(
            custom_rule_payloads(catalogue=catalogue, project_dir=project_dir)
            if custom_payloads is None
            else custom_payloads
        ),
    )


def _selected_codes(
    *, config: RulesConfig, custom_payloads: list[dict[str, object]]
) -> tuple[str, ...]:
    request: dict[str, object] = {
        "version": RULES_NATIVE_API_VERSION,
        "config": _config_payload(config),
        "custom_rules": custom_payloads,
    }
    try:
        payload: object = json.loads(
            _native.selected_codes_json(json.dumps(request, sort_keys=True, default=str))
        )
    except (ValueError, TypeError) as error:
        raise RulesError(str(error)) from error
    if not isinstance(payload, list) or any(not isinstance(code, str) for code in payload):
        raise RulesError("native rules engine returned invalid selected rule codes")
    return tuple(payload)


def render_native_owned_skill(*, content: str, input_fingerprint: str) -> str:
    """Attach Fensu schema-v2 ownership to generated guidance."""

    try:
        return _native.render_owned_skill(content, input_fingerprint)
    except (ValueError, TypeError) as error:
        raise RulesError(str(error)) from error


def native_skill_freshness(*, content: str | None, input_fingerprint: str) -> str:
    """Classify generated guidance through the Fensu ownership contract."""

    return _native.skill_freshness(content, input_fingerprint)


def _config_payload(config: RulesConfig) -> dict[str, object]:
    return asdict(config)


def _rule_selected(*, config: RulesConfig, code: str) -> bool:
    selected: bool = any(code.startswith(selector) for selector in config.select)
    ignored: bool = any(code.startswith(selector) for selector in config.ignore)
    return selected and not ignored


def custom_rule_payloads(
    *, catalogue: tuple[Rule, ...], project_dir: Path
) -> list[dict[str, object]]:
    """Describe every catalogued custom rule for native selection and evaluation."""

    closures: dict[str, tuple[Path, ...]] = {}
    return [
        _custom_rule_payload(
            rule=rule,
            project_dir=project_dir,
            import_closure=_shared_import_closure(
                rule=rule, project_dir=project_dir, cache=closures
            ),
        )
        for rule in catalogue
        if rule.custom
    ]


def _custom_rule_payload(
    *, rule: Rule, project_dir: Path, import_closure: tuple[Path, ...]
) -> dict[str, object]:
    return {
        "code": rule.code,
        "family": rule.family,
        "slug": rule.slug,
        "message": rule.message,
        "remediation": rule.remediation,
        "enabled_by_default": rule.enabled_by_default,
        "implementation_fingerprint": custom_rule_implementation_fingerprint(
            rule=rule, project_dir=project_dir, import_closure=import_closure
        ),
        **_custom_rule_source_payload(rule=rule, project_dir=project_dir),
        "project_wide": rule.project_wide,
        "check_name": getattr(rule.check, "__name__", ""),
        "test_case_count": len(custom_rule_test_evidence(rule=rule, project_dir=project_dir)),
    }


def _shared_import_closure(
    *, rule: Rule, project_dir: Path, cache: dict[str, tuple[Path, ...]]
) -> tuple[Path, ...]:
    if rule.source is None:
        return ()
    source: str = str(Path(rule.source).resolve())
    if source not in cache:
        cache[source] = custom_rule_import_closure(rule=rule, project_dir=project_dir)
    return cache[source]


def _custom_rule_source_payload(*, rule: Rule, project_dir: Path) -> dict[str, object]:
    source: str | None = rule.source
    if source is not None:
        source_path: Path = Path(source).resolve()
        root: Path = project_dir.resolve()
        if source_path.is_relative_to(root):
            source = source_path.relative_to(root).as_posix()
    try:
        source_line: int = inspect.getsourcelines(rule.check)[1]
    except (OSError, TypeError):
        source_line = 1
    check_owner: str = getattr(rule.check, "__qualname__", getattr(rule.check, "__name__", ""))
    return {
        "source": source,
        "source_line": source_line,
        "source_column": 1,
        "owner": f"{source or 'rules'}:{check_owner}",
    }


def decode_rule_finding(value: object) -> Finding:
    if not isinstance(value, dict):
        raise RulesError("native rules engine returned an invalid finding")
    payload: dict[str, object] = {str(key): item for key, item in value.items()}
    code: object = payload.get("code")
    path: object = payload.get("path")
    line: object = payload.get("line")
    column: object = payload.get("column")
    message: object = payload.get("message")
    remediation: object = payload.get("remediation")
    if (
        not isinstance(code, str)
        or not isinstance(path, str)
        or not isinstance(line, int)
        or not isinstance(column, int)
        or not isinstance(message, str)
        or not isinstance(remediation, str)
    ):
        raise RulesError("native rules engine returned an invalid finding")
    return Finding(
        code=code,
        path=Path(path),
        line=line,
        column=column,
        message=message,
        remediation=remediation,
        unevaluated=payload.get("unevaluated") is True,
        fixable=payload.get("fixable") is True,
    )


def _finding_payload(finding: Finding) -> dict[str, object]:
    return {
        "unevaluated": finding.unevaluated,
        "code": finding.code,
        "path": finding.path.as_posix(),
        "line": finding.line,
        "column": finding.column,
        "message": finding.message,
        "remediation": finding.remediation,
    }
