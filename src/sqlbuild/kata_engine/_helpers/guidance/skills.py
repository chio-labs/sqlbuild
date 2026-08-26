"""Kata agent-guidance rendering."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from sqlbuild.kata_engine._helpers.engine.native import render_native_owned_skill
from sqlbuild.kata_engine._helpers.engine.ruleset import resolve_ruleset
from sqlbuild.kata_engine._helpers.guidance.thresholds import format_threshold_lines
from sqlbuild.kata_engine.models import KataConfig, KataRule, ResolvedRuleset


def render_skills(*, config: KataConfig, project_dir: Path) -> tuple[str, str]:
    """Render stable guidance from ordinary kata catalogue resolution."""

    ruleset: ResolvedRuleset = resolve_ruleset(config=config, project_dir=project_dir)
    rules: tuple[KataRule, ...] = ruleset.rules
    body: list[str] = [
        "# SQLBuild Kata",
        "",
        "Kata enforces SQL model architecture and never modifies SQL files.",
        "Run `sqb kata` before handing off model changes.",
        "",
        "## Active Rules",
    ]
    for rule in rules:
        body.extend(
            (
                "",
                f"### {rule.code}: {rule.slug}",
                "",
                rule.message,
                "",
                f"Correct shape: {_rule_example(rule=rule)}",
                "",
                f"Remediation: {rule.remediation}",
            )
        )
        configured: Mapping[str, object] = config.rule_options.get(rule.code, {})
        effective: dict[str, object] = {
            option.name: configured.get(option.name, option.default) for option in rule.options
        }
        if effective:
            body.extend(("", f"Effective options: {effective}"))
    if config.rule_exceptions or config.rule_ignores or config.select_star_allow:
        body.extend(
            (
                "",
                "## Scoped Deviations",
                "",
            )
        )
        for entry in config.rule_exceptions:
            body.append(f"- Exception `{entry.rule}` at `{entry.path}`: {entry.reason}")
        for entry in config.rule_ignores:
            body.append(
                f"- Ignore `{','.join(entry.rules)}` at `{','.join(entry.paths)}`: {entry.reason}"
            )
        for entry in config.select_star_allow:
            body.append(f"- Lone-star allowance `{','.join(entry.paths)}`: {entry.reason}")
    if any(rule.code.startswith("SQBKX") for rule in rules):
        body.extend(("", "## Effective Thresholds", ""))
        body.extend(format_threshold_lines(config=config))
    if any(rule.code.startswith("SQBKT") for rule in rules):
        body.extend(("", "## SQL Test Paths", ""))
        body.append("- Unit tests: `tests/unit/`")
        body.append("- Scenarios: `tests/scenarios/`")
        body.append(
            f"- Cross-domain pipelines: `tests/unit/{config.sql_tests.pipeline_directory}/`"
        )
    if config.domains or config.approved_source_tokens or config.retired_source_tokens:
        body.extend(("", "## Naming Vocabulary", ""))
        body.append(f"- Domains: `{', '.join(config.domains)}`")
        body.append(f"- Approved source tokens: `{', '.join(config.approved_source_tokens)}`")
        for retired, replacement in sorted(config.retired_source_tokens.items()):
            body.append(f"- Replace retired `{retired}` with `{replacement}`")
    content: str = "\n".join(body).rstrip() + "\n"
    return (
        render_native_owned_skill(content=content, input_fingerprint=ruleset.fingerprint),
        ruleset.fingerprint,
    )


def _rule_example(*, rule: KataRule) -> str:
    examples: dict[str, str] = {
        "SQBKS101": 'WITH upstream AS (SELECT * FROM __ref("domain__stg__entity")), ...',
        "SQBKS201": "SELECT id, status FROM final; use a lone SELECT * only when allowed.",
        "SQBKL001": "stg -> int_clean -> int_enriched -> mart; skipping layers is valid.",
        "SQBKR001": "domain__int_clean__entity or domain__mart_v__entity.",
        "SQBKR401": "MODEL (contract enforced, columns (...)); declare authoritative columns.",
        "SQBKT001": "Keep unit tests in tests/unit/ and scenarios in tests/scenarios/.",
        "SQBKT002": "test_stg_orders__excludes_cancelled.sql and daily_revenue__minimal.sql.",
        "SQBKT003": "models/staging/stg_orders.sql maps to tests/unit/staging/.",
        "SQBKT004": 'TEST (name "stg_orders: excludes cancelled orders");',
        "SQBKT101": 'SCENARIO (description "Daily revenue includes successful payments");',
        "SQBKX001": "Attach not_null/unique audits to the model key.",
    }
    if rule.guidance is not None:
        return rule.guidance.good_example
    return examples.get(rule.code, f"Apply `{rule.slug}` at the SQL node named by the fault.")
