"""Compiler Rules end-to-end fixture helpers."""

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
    *, project_dir: Path, selected_rules: tuple[str, ...], files: tuple[tuple[str, str], ...]
) -> None:
    """Write a DuckDB project whose selected custom Rules live in the given files."""

    (project_dir / "sqlbuild_project.toml").write_text(
        f'name = "orders"\nadapter = "duckdb"\n\n[rules]\nselect = {json.dumps(selected_rules)}\n'
        "\n[rules.thresholds]\nmin_custom_rule_test_cases = 0\n",
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
    project_dir: Path, *, environment: tuple[tuple[str, str], ...] = ()
) -> subprocess.CompletedProcess[str]:
    """Run the real `sqb compile --json` command with extra parent environment variables."""

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
