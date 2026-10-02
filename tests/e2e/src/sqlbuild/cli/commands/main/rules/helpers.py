"""Compiler Rules end-to-end fixture helpers."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.rules_benchmark._helpers.custom_rules import write_custom_rules

__all__ = ("write_custom_rules",)


def write_unevaluated_rules_project(
    *,
    project_dir: Path,
    model_options: str = "",
    configuration: str = "",
    adapter: str = "duckdb",
    selected_rules: tuple[str, ...] = ("SQBRSQL035",),
    resource_path: str = "models/staging/orders.sql",
    resource_template: str = "MODEL ({options});\nSELECT {expression} AS order_id",
    extra_files: tuple[tuple[str, str], ...] = (),
) -> None:
    (project_dir / "sqlbuild_project.toml").write_text(
        f'name = "orders"\nadapter = "{adapter}"\n[rules]\nselect = {json.dumps(selected_rules)}\n'
        + configuration
    )
    models: Path = project_dir / "models/staging"
    models.mkdir(parents=True)
    (models / "orders.sql").write_text("MODEL ();\nSELECT 1 AS order_id\n")
    relative_path: str
    contents: str
    for relative_path, contents in extra_files:
        extra: Path = project_dir / relative_path
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_text(contents)
    resource: Path = project_dir / resource_path
    resource.parent.mkdir(parents=True, exist_ok=True)
    resource.write_text(
        resource_template.format(options=model_options, expression="ABS(" * 130 + "1" + ")" * 130)
    )


def run_unevaluated_rules_cli(project_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(Path(sys.executable).with_name("sqb")),
            "--no-color",
            "--project-dir",
            str(project_dir),
            *args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def write_custom_rule_project(
    *,
    project_dir: Path,
    selected_rules: tuple[str, ...],
    files: tuple[tuple[str, str], ...],
    configuration: str = "",
) -> None:
    """Write a DuckDB project whose selected custom Rules live in the given files."""

    (project_dir / "sqlbuild_project.toml").write_text(
        f'name = "orders"\nadapter = "duckdb"\n\n[rules]\nselect = {json.dumps(selected_rules)}\n'
        "\n[rules.thresholds]\nmin_custom_rule_test_cases = 0\n" + configuration,
        encoding="utf-8",
    )
    orders: Path = project_dir / "models" / "orders.sql"
    orders.parent.mkdir(parents=True, exist_ok=True)
    orders.write_text('MODEL (description "Orders");\nSELECT 1 AS order_id\n', encoding="utf-8")
    relative_path: str
    contents: str
    for relative_path, contents in files:
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")


CUSTOM_RULE_HEADER: str = (
    "import pathlib\n\nfrom sqlbuild.rules import Finding, Model, RuleContext, rule\n"
)


def custom_rule_source(*, code: str, body: str, header: str = CUSTOM_RULE_HEADER) -> str:
    """Return one model-subject custom Rule module with the given check body."""

    return (
        f"{header}\n\n"
        f'@rule(code="{code}", message="orders rule", remediation="Adjust the orders model.")\n'
        "def check(*, model: Model, ctx: RuleContext) -> list[Finding]:\n"
        f"{body}"
    )


def run_compile_cli(
    project_dir: Path,
    *,
    environment: tuple[tuple[str, str], ...] = (),
    working_directory: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the real `sqb compile --json` command from an optional invocation directory."""

    return subprocess.run(
        [
            str(Path(sys.executable).with_name("sqb")),
            "--no-color",
            "--project-dir",
            str(project_dir),
            "compile",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **dict(environment)},
        cwd=working_directory,
    )


def custom_rule_diagnostics(result: subprocess.CompletedProcess[str]) -> list[dict[str, Any]]:
    """Return custom-rule diagnostics from one JSON compile result."""

    payload: dict[str, Any] = json.loads(result.stdout)
    return list(filter(lambda item: str(item["code"]).startswith("XSQBR"), payload["diagnostics"]))


def custom_rule_codes(result: subprocess.CompletedProcess[str]) -> tuple[str, ...]:
    """Return custom-rule diagnostic codes from one JSON compile result."""

    return tuple(str(item["code"]) for item in custom_rule_diagnostics(result))


def custom_rule_paths(result: subprocess.CompletedProcess[str]) -> tuple[str, ...]:
    """Return sorted custom-rule diagnostic paths from one JSON compile result."""

    return tuple(sorted(str(item["path"]) for item in custom_rule_diagnostics(result)))


def rule_cache_hits(result: subprocess.CompletedProcess[str]) -> int:
    """Return the Rules cache hit count from one JSON compile result."""

    return int(json.loads(result.stdout)["compile_timings"]["rule_cache_hits"])


def string_set_order(*, names: tuple[str, ...], hash_seed: str) -> str:
    """Return the comma-joined iteration order of a string set under one hash seed."""

    return subprocess.run(
        [sys.executable, "-c", f"print(','.join({{*{list(names)!r}}}))"],
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONHASHSEED": hash_seed},
    ).stdout.strip()


def custom_rule_messages(result: subprocess.CompletedProcess[str]) -> tuple[str, ...]:
    """Return custom-rule diagnostic messages from one JSON compile result."""

    return tuple(str(item["message"]) for item in custom_rule_diagnostics(result))


def write_quality_project(*, project_dir: Path, toml: str, upstream: str, summary: str) -> None:
    """Write a two-model project: `raw_orders` and the `order_summary` model under test."""

    (project_dir / "sqlbuild_project.toml").write_text(toml, encoding="utf-8")
    models: Path = project_dir / "models"
    models.mkdir()
    (models / "raw_orders.sql").write_text(upstream, encoding="utf-8")
    (models / "order_summary.sql").write_text(summary, encoding="utf-8")


def diagnostic_codes(result: subprocess.CompletedProcess[str]) -> tuple[str, ...]:
    """Return diagnostic codes from one JSON compile result, in report order."""

    return tuple(str(item["code"]) for item in json.loads(result.stdout)["diagnostics"])


def finding_fixability(result: subprocess.CompletedProcess[str]) -> dict[str, bool]:
    """Map each code in a `rules --json run` result to whether its finding reports a fix."""

    return {
        str(item["code"]): item.get("fixable") is True
        for item in json.loads(result.stdout)["findings"]
    }


def fixable_finding_count(result: subprocess.CompletedProcess[str]) -> int:
    """Count findings that report an available fix in a `rules --json run` result."""

    return sum(item.get("fixable") is True for item in json.loads(result.stdout)["findings"])


def diagnostic_notes(result: subprocess.CompletedProcess[str]) -> dict[str, tuple[str, ...]]:
    """Map each code in a JSON compile result to its diagnostic notes."""

    return {
        str(item["code"]): tuple(item.get("notes", ()))
        for item in json.loads(result.stdout)["diagnostics"]
    }


def help_fragment_presence(
    result: subprocess.CompletedProcess[str], fragments: tuple[tuple[str, str], ...]
) -> tuple[bool, ...]:
    """Return, per `(code, fragment)`, whether that code's diagnostic help contains it."""

    helps: dict[str, str] = {
        str(item["code"]): str(item.get("help", ""))
        for item in json.loads(result.stdout)["diagnostics"]
    }
    return tuple(fragment in helps.get(code, "") for code, fragment in fragments)


def long_literal_hints(result: subprocess.CompletedProcess[str]) -> dict[str, str]:
    """Map each finding path of a SQBRSQL044-only run to the help before the generic guidance."""

    return {
        str(item["path"]): str(item["remediation"]).partition("Define the value once")[0].strip()
        for item in json.loads(result.stdout)["findings"]
    }


INCREMENTAL_RULES_PROJECT: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "orders"\nadapter = "duckdb"\ndefault_target = "dev"\n\n'
        '[connection]\ndatabase = "warehouse.duckdb"\n\n'
        '[targets.dev]\nschema = "dev"\n\n[targets.prod]\nschema = "prod"\n\n'
        '[vars]\ndiscount_rate = "0.1"\n\n'
        '[rules]\nselect = ["SQBR", "XSQBR"]\n\n'
        "[rules.thresholds]\nmin_custom_rule_test_cases = 0\n"
    ),
    "models/staging/stg_orders.sql": (
        "MODEL (\n  materialized view,\n  contract enforced,\n  columns (\n"
        "    order_id (type INTEGER, nullable false, audits [not_null]),\n"
        "    amount (type DOUBLE),\n  ),\n);\n\n"
        "SELECT CAST(1 AS INTEGER) AS order_id, CAST(10.5 AS DOUBLE) AS amount\n"
    ),
    "models/marts/order_totals.sql": (
        "MODEL (\n  columns (\n"
        "    order_id (type INTEGER, nullable false, audits [not_null]),\n"
        "    net_amount (type DOUBLE),\n  ),\n);\n\n"
        "SELECT\n  o.order_id,\n"
        '  CAST(@discounted("o.amount") * (1 - CAST(@@discount_rate AS DOUBLE)) AS DOUBLE)'
        " AS net_amount\n"
        'FROM __ref("stg_orders") AS o\n'
    ),
    "models/marts/_sqlbuild/_macros/amounts.py": (
        'def discounted(amount: str) -> str:\n    return f"({amount}) * 0.9"\n'
    ),
    "tests/unit/test_order_totals.sql": (
        "TEST ();\n\nWITH\n__ref__stg_orders AS (\n  SELECT 1 AS order_id, 10.0 AS amount\n),\n"
        "__expected__order_totals AS (\n  SELECT 1 AS order_id, 9.0 AS net_amount\n)\n"
        "SELECT 1\n"
    ),
    "config/policy.yml": "strict: false\n",
    "rules/limits.py": "MAX_NAME_LENGTH: int = 30\n",
    "rules/memo.py": """from sqlbuild.rules import Finding, Model, RuleContext, rule

_SEEN_SQL: dict[str, str] = {}


@rule(code="XSQBRGOV005", message="Models must not repeat SQL", remediation="Deduplicate.")
def unique_sql(*, model: Model, ctx: RuleContext) -> list[Finding]:
    if not _SEEN_SQL:
        for item in ctx.project.models:
            _SEEN_SQL[item.name] = ctx.sql.for_model(item).expanded.source
    own: str = _SEEN_SQL[model.name]
    repeated: bool = sum(source == own for source in _SEEN_SQL.values()) > 1
    return [ctx.finding(subject=model)] if repeated else []
""",
    "rules/governance.py": """from sqlbuild.rules import Finding, Model, Project, RuleContext, rule

from rules import limits


@rule(code="XSQBRGOV001", message="Contracts must be enforced", remediation="Enforce it.")
def enforced_contracts(*, model: Model, ctx: RuleContext) -> list[Finding]:
    if "SELECT" not in ctx.sql.for_model(model).authored.source:
        return []
    return [] if ctx.contracts.enforced(model) else [ctx.finding(subject=model)]


@rule(code="XSQBRGOV002", message="Staging models need a consumer", remediation="Use it.")
def staging_consumers(*, model: Model, ctx: RuleContext) -> list[Finding]:
    if not model.name.startswith("stg_"):
        return []
    return [] if ctx.graph.dependents(model) else [ctx.finding(subject=model)]


@rule(code="XSQBRGOV003", message="Strict policy limits models", remediation="Relax it.")
def strict_policy(*, project: Project, ctx: RuleContext) -> list[Finding]:
    del project
    findings: list[Finding] = []
    if "strict: true" in ctx.project.tree.read_text("config/policy.yml"):
        findings.append(ctx.finding(subject="config/policy.yml", message="strict policy"))
    if len(ctx.project.tree.glob("config/*.yml")) > 1:
        findings.append(ctx.finding(subject="config/policy.yml", message="several policies"))
    if len(ctx.project.models) > 2:
        findings.append(ctx.finding(subject="config/policy.yml", message="too many models"))
    return findings


@rule(code="XSQBRGOV004", message="Model names are bounded", remediation="Shorten it.")
def bounded_names(*, model: Model, ctx: RuleContext) -> list[Finding]:
    names: list[str] = [test.name for test in ctx.tests.for_model(model)]
    too_long: bool = len(model.name) > limits.MAX_NAME_LENGTH
    unnamed: bool = any("discount" not in name for name in names)
    return [ctx.finding(subject=model)] if too_long or unnamed else []


@rule(code="XSQBRGOV006", message="Expanded SQL uses a flagged value", remediation="Review.")
def flagged_values(*, model: Model, ctx: RuleContext) -> list[Finding]:
    expanded: str = ctx.sql.for_model(model).expanded.source
    flagged: bool = any(value in expanded for value in ("12.5", "0.8", "0.2"))
    return [ctx.finding(subject=model)] if flagged else []
""",
}


def write_project_files(*, project_dir: Path, files: dict[str, str]) -> None:
    """Write authored project files beneath one project directory."""

    for relative_path, contents in files.items():
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")


def rules_compile_outcome(project_dir: Path, *arguments: str) -> tuple[int, str, str]:
    """Compile in a fresh process and return its exit code, diagnostics, and artifacts digest."""

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            str(Path(sys.executable).with_name("sqb")),
            "--no-color",
            "--project-dir",
            str(project_dir),
            "compile",
            "--json",
            *arguments,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    payload: dict[str, Any] = json.loads(result.stdout or "{}")
    artifacts: Any = hashlib.sha256()
    compiled: Path = project_dir / "target" / "compiled"
    for path in sorted(filter(Path.is_file, compiled.rglob("*"))):
        artifacts.update(path.relative_to(compiled).as_posix().encode())
        artifacts.update(path.read_bytes())
    return (
        result.returncode,
        json.dumps(payload.get("diagnostics"), sort_keys=True),
        artifacts.hexdigest(),
    )


def rule_cache_counts(project_dir: Path) -> tuple[int, int]:
    """Return rule cache hits and misses of one fresh-process compile."""

    result: subprocess.CompletedProcess[str] = run_compile_cli(project_dir)
    timings: dict[str, int] = json.loads(result.stdout)["compile_timings"]
    return timings["rule_cache_hits"], timings["rule_cache_misses"]
