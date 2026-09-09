"""Rules agent-guidance rendering."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from sqlbuild.rule_engine._helpers.engine.native import render_native_owned_skill
from sqlbuild.rule_engine._helpers.engine.ruleset import resolve_ruleset
from sqlbuild.rule_engine._helpers.guidance.thresholds import format_threshold_lines
from sqlbuild.rule_engine.constants import (
    RULES_LAYOUT_RULE_PREFIXES,
    RULES_LAYOUT_THRESHOLD_RULE_CODES,
    RULES_THRESHOLD_RULE_CODES,
)
from sqlbuild.rule_engine.models import ResolvedRuleset, Rule, RulesConfig


def render_skills(*, config: RulesConfig, project_dir: Path) -> tuple[str, str]:
    """Render stable guidance from ordinary rules catalogue resolution."""

    ruleset: ResolvedRuleset = resolve_ruleset(config=config, project_dir=project_dir)
    rules: tuple[Rule, ...] = ruleset.rules
    body: list[str] = [
        "# SQLBuild Rules",
        "",
        "Rules enforce SQL model architecture and never modifies SQL files.",
        "Run `sqb rules run SQBR` before handing off model changes.",
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
    if any(
        rule.code in RULES_THRESHOLD_RULE_CODES or rule.code in RULES_LAYOUT_THRESHOLD_RULE_CODES
        for rule in rules
    ):
        body.extend(("", "## Effective Thresholds", ""))
        body.extend(format_threshold_lines(config=config))
    if any(rule.code.startswith(RULES_LAYOUT_RULE_PREFIXES) for rule in rules):
        body.extend(("", "## Owner Layout", ""))
        body.append(f"- Configured levels: `{', '.join(config.layout.levels)}`")
        body.append("- Every model owner is a leaf or a branch, never both.")
        body.append("- Declaration-role buckets organize files without changing visibility.")
    if any(rule.code.startswith("SQBRTEST") for rule in rules):
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


def _rule_example(*, rule: Rule) -> str:
    examples: dict[str, str] = {
        "SQBRMODEL101": 'WITH upstream AS (SELECT * FROM __ref("domain__stg__entity")), ...',
        "SQBRMODEL102": "SELECT id, status FROM final; use a lone SELECT * only when allowed.",
        "SQBRGRAPH101": "stg -> int_clean -> int_enriched -> mart; skipping layers is valid.",
        "SQBRPROJECT101": "domain__int_clean__entity or domain__mart_v__entity.",
        "SQBRCONTRACT101": (
            "MODEL (contract enforced, columns (...)); declare authoritative columns."
        ),
        "SQBRPROJECT202": "domain/level/owner contains models or child owners, never both.",
        "SQBRPROJECT201": "models/<domain>/<configured-level>/model.sql resolves one domain root.",
        "SQBRPROJECT203": "domain/level/subdomain/model.sql at the default depth of one.",
        "SQBRPROJECT204": "order_status and order_status_history consolidate under order_status.",
        "SQBRDECLARATION302": "_macros/ is flat, or every file uses one concern bucket.",
        "SQBRDECLARATION303": "_macros/normalisation/names.py uses one default bucket level.",
        "SQBRDECLARATION304": "Keep each flat role or concern bucket within its file cap.",
        "SQBRDECLARATION305": "Use temporal/ or scoring/, not utils/ or common/.",
        "SQBRDECLARATION306": "Group normalise_order.py and normalise_person.py under normalise/.",
        "SQBRTEST101": "Keep unit tests in tests/unit/ and scenarios in tests/scenarios/.",
        "SQBRTEST102": "test_stg_orders__excludes_cancelled.sql and daily_revenue__minimal.sql.",
        "SQBRTEST103": "models/staging/stg_orders.sql maps to tests/unit/staging/.",
        "SQBRTEST104": 'TEST (name "stg_orders__excludes_cancelled_orders");',
        "SQBRTEST105": 'SCENARIO (description "Daily revenue includes successful payments");',
        "SQBRTEST201": "Attach not_null/unique audits to the model key.",
    }
    if rule.guidance is not None:
        return rule.guidance.good_example
    return examples.get(rule.code, f"Apply `{rule.slug}` at the SQL node named by the finding.")
