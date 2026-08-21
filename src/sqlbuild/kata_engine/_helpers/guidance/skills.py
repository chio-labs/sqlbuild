"""Kata agent-guidance rendering."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from sqlbuild.kata_engine._helpers.engine.ruleset import resolve_ruleset
from sqlbuild.kata_engine.constants import KATA_THRESHOLD_DEFAULTS
from sqlbuild.kata_engine.models import KataConfig, KataRule, ResolvedRuleset


def render_skills(*, config: KataConfig, project_dir: Path) -> str:
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
        if configured:
            body.extend(("", f"Effective options: {configured}"))
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
    if any(rule.code.startswith("KTX") for rule in rules):
        body.extend(("", "## Effective Thresholds", ""))
        thresholds: dict[str, int] = {**KATA_THRESHOLD_DEFAULTS, **config.thresholds}
        for name, value in sorted(thresholds.items()):
            body.append(f"- `{name}` = `{value}`")
    if config.domains or config.approved_source_tokens or config.retired_source_tokens:
        body.extend(("", "## Naming Vocabulary", ""))
        body.append(f"- Domains: `{', '.join(config.domains)}`")
        body.append(f"- Approved source tokens: `{', '.join(config.approved_source_tokens)}`")
        for retired, replacement in sorted(config.retired_source_tokens.items()):
            body.append(f"- Replace retired `{retired}` with `{replacement}`")
    content: str = "\n".join(body).rstrip() + "\n"
    return f"<!-- kata-policy: {ruleset.fingerprint} -->\n{content}"


def _rule_example(*, rule: KataRule) -> str:
    examples: dict[str, str] = {
        "KTS101": 'WITH upstream AS (SELECT * FROM __ref("domain__stg__entity")), ...',
        "KTS201": "SELECT id, status FROM final; use a lone SELECT * only when allowed.",
        "KTL001": "stg -> int_clean -> int_enriched -> mart; skipping layers is valid.",
        "KTR001": "domain__int_clean__entity or domain__mart_v__entity.",
        "KTR401": "MODEL (contract enforced, columns (...)); declare authoritative columns.",
        "KTX001": "Attach not_null/unique audits to the model key.",
        "KTX002": "Mock imports, assert __expected__<model>, then mutation-check the test.",
    }
    return examples.get(rule.code, f"Apply `{rule.slug}` at the SQL node named by the fault.")
