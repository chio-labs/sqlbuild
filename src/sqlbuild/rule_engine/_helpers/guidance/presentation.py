"""Deterministic rules result and rule rendering."""

from __future__ import annotations

from sqlbuild.rule_engine._helpers.guidance.thresholds import format_threshold_lines
from sqlbuild.rule_engine.models import Rule, RulesConfig

_MINIMUM_RULES_CODES: frozenset[str] = frozenset({"SQBRTEST201", "SQBRTEST202"})


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
