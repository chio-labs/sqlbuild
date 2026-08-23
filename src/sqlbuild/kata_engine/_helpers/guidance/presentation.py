"""Deterministic kata result and rule rendering."""

from __future__ import annotations

import json

from sqlbuild.kata_engine.models import KataResult, KataRule


def format_result_text(*, result: KataResult) -> str:
    if not result.faults:
        return (
            f"Kata passed: {result.evaluated_models} models evaluated, 0 faults "
            f"({result.cache_hits} cache hits, {result.cache_misses} misses)"
        )
    blocks: list[str] = []
    for fault in result.faults:
        blocks.append(
            f"{fault.path}:{fault.line}:{fault.column} [{fault.code}] {fault.message}\n"
            f"  Remediation: {fault.remediation}"
        )
    blocks.append(f"Found {len(result.faults)} kata faults")
    return "\n".join(blocks)


def format_result_json(*, result: KataResult) -> str:
    faults: list[dict[str, object]] = []
    for fault in result.faults:
        faults.append(
            {
                "code": fault.code,
                "path": fault.path.as_posix(),
                "line": fault.line,
                "column": fault.column,
                "message": fault.message,
                "remediation": fault.remediation,
            }
        )
    payload: dict[str, object] = {
        "evaluated_models": result.evaluated_models,
        "cache_hits": result.cache_hits,
        "cache_misses": result.cache_misses,
        "fault_count": len(result.faults),
        "faults": faults,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def format_rule_text(*, rule: KataRule) -> str:
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
    return "\n".join(lines)
