"""Builders for custom-rule host partitioning tests."""

from collections.abc import Callable
from dataclasses import replace
from operator import attrgetter
from pathlib import Path

import pytest

import sqlbuild._native as native_module
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.rule_engine._helpers.engine.catalogue import build_catalogue
from sqlbuild.rule_engine._helpers.engine.custom_rules import evaluate_custom_rules_cached
from sqlbuild.rule_engine._helpers.host import custom_host_pool
from sqlbuild.rule_engine.models import CustomRulesOutcome, Rule, RulesCacheConfig, RulesConfig
from tests.unit.src.sqlbuild.rule_engine.main.evaluate.helpers import build_project

_MODEL_RULE: str = "XSQBRT101"
_PROJECT_RULE: str = "XSQBRT102"
_RULES_MODULE: str = f'''from sqlbuild.rules import Finding, Model, Project, RuleContext, rule


@rule(code="{_MODEL_RULE}", message="order models need an even suffix", remediation="Rename it.")
def even_suffix(*, model: Model, ctx: RuleContext) -> list[Finding]:
    if model.name in FAILING:
        raise ValueError(f"cannot inspect {{model.name}}")
    if RECORD_SEEN:
        SEEN[model.name] = True
    source: str = ctx.sql.for_model(model).expanded.source
    return [ctx.finding(subject=model)] if "odd" in source else []


@rule(code="{_PROJECT_RULE}", message="projects need few models", remediation="Split it.")
def few_models(*, project: Project, ctx: RuleContext) -> list[Finding]:
    del project
    first: Model = ctx.project.models[0]
    return [ctx.finding(subject=first)] if len(ctx.project.models) > 3 else []
'''
_PARITIES: tuple[str, str] = ("even", "odd")


def write_order_rules(
    *, root: Path, failing: tuple[str, ...] = (), records_module_state: bool = False
) -> None:
    """Write one model rule and one project rule, optionally failing or keeping module state."""

    rules: Path = root / "rules" / "orders.py"
    rules.parent.mkdir(parents=True, exist_ok=True)
    rules.write_text(
        f"FAILING = {set(failing)!r}\nRECORD_SEEN = {records_module_state!r}\n"
        f"SEEN: dict[str, bool] = {{}}\n{_RULES_MODULE}",
        encoding="utf-8",
    )


def orders_project(*, model_count: int, edits: dict[str, str] | None = None) -> CompiledProject:
    """Return numbered order models whose SQL marks them odd or even, with optional edits."""

    sql_by_name: dict[str, str] = {
        f"orders_{index:03d}": f"SELECT 1 AS order_id -- {_PARITIES[index % 2]}"
        for index in range(model_count)
    }
    sql_by_name.update(edits or {})
    projects: list[CompiledProject] = [
        build_project(name=name, relative_path=f"models/{name}.sql", sql=sql, config_values={})
        for name, sql in sql_by_name.items()
    ]
    return replace(projects[0], models=tuple(project.models[0] for project in projects))


def evaluate_order_rules(
    *, project: CompiledProject, root: Path, cache_enabled: bool = True
) -> CustomRulesOutcome:
    """Evaluate both order rules through the incremental custom-rule cache."""

    config: RulesConfig = RulesConfig(
        select=(_MODEL_RULE, _PROJECT_RULE), cache=RulesCacheConfig(enabled=cache_enabled)
    )
    rules: tuple[Rule, ...] = tuple(
        filter(attrgetter("custom"), build_catalogue(config=config, project_dir=root))
    )
    return evaluate_custom_rules_cached(
        project=project, config=config, project_dir=root, rules=rules, dialect="duckdb"
    )


def use_hosts(*, monkeypatch: pytest.MonkeyPatch, hosts: int) -> list[str]:
    """Allow up to `hosts` host processes for any plan and record every host launch."""

    launches: list[str] = []
    launch: Callable[[str], str] = native_module.run_custom_host_json

    def recording_launch(spec_json: str) -> str:
        launches.append(spec_json)
        return launch(spec_json)

    monkeypatch.setattr(custom_host_pool, "_MIN_INVOCATIONS_PER_HOST", 1)
    monkeypatch.setattr(custom_host_pool, "_available_cores", lambda: hosts)
    monkeypatch.setattr(native_module, "run_custom_host_json", recording_launch)
    return launches
