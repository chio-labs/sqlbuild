"""Typed Python adapter for the private native rules engine."""

from __future__ import annotations

import inspect
import json
from dataclasses import asdict
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild._native import (
    custom_rule_implementation_fingerprint,
    custom_rule_import_closure,
    custom_rule_test_evidence,
)
from sqlbuild.rule_engine._helpers.run.native_rows import (
    finalize_rules_rows,
)
from sqlbuild.rule_engine.constants import (
    RULES_NATIVE_API_VERSION,
)
from sqlbuild.rule_engine.exceptions import RulesError
from sqlbuild.rule_engine.models import (
    Finding,
    Rule,
    RulesConfig,
)


def finalize_native_findings(
    *,
    config: RulesConfig,
    project_dir: Path,
    evaluated_codes: tuple[str, ...],
    findings: tuple[Finding, ...],
) -> tuple[Finding, ...]:
    """Apply exception policy once to completed SQL, native, and custom findings."""

    return finalize_rules_rows(
        config=config,
        project_dir=project_dir,
        evaluated_codes=evaluated_codes,
        findings=findings,
    )


def native_selected_codes(
    *,
    config: RulesConfig,
    catalogue: tuple[Rule, ...],
    project_dir: Path,
    custom_payloads: list[dict[str, object]] | None = None,
) -> tuple[str, ...]:
    """Resolve the active ruleset through the native Fensu adapter."""

    return selected_codes(
        config=config,
        custom_payloads=(
            custom_rule_payloads(catalogue=catalogue, project_dir=project_dir)
            if custom_payloads is None
            else custom_payloads
        ),
    )


def selected_codes(
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


def rule_selected(*, config: RulesConfig, code: str) -> bool:
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
