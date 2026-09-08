"""Isolated Python host for selected repository-defined policy rules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from sqlbuild.policy_engine.classes.rule_context import EvaluationRuleContext
from sqlbuild.policy_engine.exceptions import PolicyError
from sqlbuild.policy_engine.models import PolicyConfig, PolicyFault, PolicyRule


def evaluate_custom_rules(
    *,
    project: CompiledProject,
    config: PolicyConfig,
    project_dir: Path,
    selected_rules: tuple[PolicyRule, ...],
    dialect: str = "generic",
    selected_model_paths: frozenset[str] | None = None,
) -> list[PolicyFault]:
    """Run only selected custom rules through the Python authoring API."""

    custom_rules: tuple[PolicyRule, ...] = tuple(rule for rule in selected_rules if rule.custom)
    if not custom_rules:
        return []
    polyglot: Any | None = import_polyglot_sql()
    if polyglot is None:
        raise PolicyError("custom policy rules require the bundled polyglot_sql package")
    faults: list[PolicyFault] = []
    models: tuple[CompiledModel, ...] = tuple(
        model
        for model in sorted(project.models, key=lambda item: item.relative_path.as_posix())
        if selected_model_paths is None or model.relative_path.as_posix() in selected_model_paths
    )
    for model_index, model in enumerate(models):
        try:
            ast: Any = polyglot.parse_one(model.query_sql, dialect=dialect)
        except Exception as error:
            raise PolicyError(
                f"could not parse {model.relative_path} for policy: {error}"
            ) from error
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
                raise PolicyError(
                    f"policy rule {rule.code} failed for {model.relative_path}: {error}"
                ) from error
    return faults
