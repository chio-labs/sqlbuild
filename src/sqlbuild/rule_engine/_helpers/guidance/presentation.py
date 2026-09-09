"""Deterministic rules result and rule rendering."""

from __future__ import annotations

import json

from sqlbuild.rule_engine._helpers.guidance.thresholds import format_threshold_lines
from sqlbuild.rule_engine.models import Rule, RulesConfig, RulesResult

_MINIMUM_RULES_CODES: frozenset[str] = frozenset({"SQBRTEST201", "SQBRTEST202"})


def format_result_text(*, result: RulesResult) -> str:
    if not result.findings:
        return (
            f"Rules passed: {result.evaluated_models} models evaluated, 0 findings "
            f"({result.cache_hits} cache hits, {result.cache_misses} misses)"
        )
    blocks: list[str] = []
    for finding in result.findings:
        blocks.append(
            f"{finding.path}:{finding.line}:{finding.column} "
            f"[{finding.code}] {finding.message}\n"
            f"  Remediation: {finding.remediation}"
        )
    blocks.append(f"Found {len(result.findings)} Rules findings")
    return "\n".join(blocks)


def format_result_json(*, result: RulesResult) -> str:
    findings: list[dict[str, object]] = []
    for finding in result.findings:
        findings.append(
            {
                "code": finding.code,
                "path": finding.path.as_posix(),
                "line": finding.line,
                "column": finding.column,
                "message": finding.message,
                "remediation": finding.remediation,
            }
        )
    payload: dict[str, object] = {
        "evaluated_models": result.evaluated_models,
        "cache_hits": result.cache_hits,
        "cache_misses": result.cache_misses,
        "finding_count": len(result.findings),
        "findings": findings,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def format_rule_text(*, rule: Rule, config: RulesConfig | None = None) -> str:
    lines: list[str] = [
        f"{rule.code}: {rule.slug}",
        f"Family: {rule.family}",
        f"Enabled by default: {'yes' if rule.enabled_by_default else 'no'}",
        f"Kind: {'custom' if rule.custom else 'built-in'}",
        "",
        rule.message,
        "",
        f"Remediation: {rule.remediation}",
    ]
    if rule.source is not None:
        lines.extend(("", f"Source: {rule.source}"))
    if rule.options:
        lines.extend(("", "Options:"))
        for option in rule.options:
            lines.append(f"- {option.name}: default={option.default!r} ({option.description})")
    if config is not None and rule.code in _MINIMUM_RULES_CODES:
        lines.extend(("", "Effective thresholds:", *format_threshold_lines(config=config)))
    if config is not None and rule.code.startswith("SQBRTEST"):
        lines.extend(
            (
                "",
                "Effective SQL test paths:",
                "- Unit tests: tests/unit/",
                "- Scenarios: tests/scenarios/",
                f"- Cross-domain pipelines: tests/unit/{config.sql_tests.pipeline_directory}/",
            )
        )
    return "\n".join(lines)
