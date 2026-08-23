"""Isolated Python host for selected repository-defined kata rules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from sqlbuild.kata_engine.classes.rule_context import EvaluationRuleContext
from sqlbuild.kata_engine.exceptions import KataError
from sqlbuild.kata_engine.models import KataConfig, KataFault, KataRule


def evaluate_custom_rules(
    *,
    project: CompiledProject,
    config: KataConfig,
    project_dir: Path,
    selected_rules: tuple[KataRule, ...],
) -> list[KataFault]:
    """Run only selected custom rules through the Python authoring API."""

    custom_rules: tuple[KataRule, ...] = tuple(rule for rule in selected_rules if rule.custom)
    if not custom_rules:
        return []
    polyglot: Any | None = import_polyglot_sql()
    if polyglot is None:
        raise KataError("custom kata rules require the bundled polyglot_sql package")
    faults: list[KataFault] = []
    models: tuple[CompiledModel, ...] = tuple(
        sorted(project.models, key=lambda item: item.relative_path.as_posix())
    )
    for model_index, model in enumerate(models):
        try:
            ast: Any = polyglot.parse_one(model.query_sql, dialect="generic")
        except Exception as error:
            raise KataError(f"could not parse {model.relative_path} for kata: {error}") from error
        for rule in custom_rules:
            if rule.project_wide and model_index != 0:
                continue
            ctx: EvaluationRuleContext = EvaluationRuleContext(
                model=model,
                ast=ast,
                rule=rule,
                config=config,
                project=project,
                project_dir=project_dir,
                selected_rules=selected_rules,
                is_project_anchor=model_index == 0,
            )
            try:
                faults.extend(rule.check(model=model, ctx=ctx))
            except Exception as error:
                raise KataError(
                    f"kata rule {rule.code} failed for {model.relative_path}: {error}"
                ) from error
    return faults
