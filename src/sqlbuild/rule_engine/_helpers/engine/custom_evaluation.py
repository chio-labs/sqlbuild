"""Isolated Python host for selected repository-defined rules."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.rule_engine.classes.project_tree import public_model
from sqlbuild.rule_engine.classes.rule_context import (
    EvaluationRuleContext,
    RuleFactViews,
    build_rule_fact_views,
)
from sqlbuild.rule_engine.exceptions import RulesError
from sqlbuild.rule_engine.models import Finding, Model, Project, Rule, RulesConfig
from sqlbuild.rule_engine.types import RuleSubject


def evaluate_custom_rules(
    *,
    project: CompiledProject,
    config: RulesConfig,
    project_dir: Path,
    selected_rules: tuple[Rule, ...],
    dialect: str = "generic",
    selected_model_paths: frozenset[str] | None = None,
) -> list[Finding]:
    """Run only selected custom rules through the Python authoring API."""

    custom_rules: tuple[Rule, ...] = tuple(rule for rule in selected_rules if rule.custom)
    if not custom_rules:
        return []
    findings: list[Finding] = []
    models: tuple[CompiledModel, ...] = tuple(
        model
        for model in sorted(project.models, key=lambda item: item.relative_path.as_posix())
        if selected_model_paths is None or model.relative_path.as_posix() in selected_model_paths
    )
    project_rules: tuple[Rule, ...] = tuple(
        rule for rule in custom_rules if rule.subject is RuleSubject.PROJECT
    )
    model_rules: tuple[Rule, ...] = tuple(
        rule for rule in custom_rules if rule.subject is RuleSubject.MODEL
    )
    facts: RuleFactViews = build_rule_fact_views(
        project=project, project_dir=project_dir, dialect=dialect
    )
    model_contexts: tuple[tuple[Rule, EvaluationRuleContext], ...] = tuple(
        (
            rule,
            EvaluationRuleContext(
                model=None,
                rule=rule,
                config=config,
                project=project,
                project_dir=project_dir,
                selected_rules=selected_rules,
                dialect=dialect,
                facts=facts,
            ),
        )
        for rule in model_rules
    )
    for rule in project_rules:
        ctx: EvaluationRuleContext = EvaluationRuleContext(
            model=None,
            rule=rule,
            config=config,
            project=project,
            project_dir=project_dir,
            selected_rules=selected_rules,
            dialect=dialect,
            facts=facts,
        )
        try:
            findings.extend(
                _invoke(
                    rule=rule,
                    subject=Project(
                        model_count=len(project.models),
                        target_name=project.effective_target_name,
                    ),
                    ctx=ctx,
                )
            )
        except Exception as error:
            raise RulesError(f"rule {rule.code} failed for the project: {error}") from error
    for model in models:
        subject: Model = public_model(model)
        for rule, ctx in model_contexts:
            try:
                findings.extend(_invoke(rule=rule, subject=subject, ctx=ctx))
            except Exception as error:
                raise RulesError(
                    f"rule {rule.code} failed for {model.relative_path}: {error}"
                ) from error
    return findings


def _invoke(*, rule: Rule, subject: object, ctx: EvaluationRuleContext) -> list[Finding]:
    if rule.subject_parameter is None or rule.context_parameter is None:
        raise RulesError(f"custom rule {rule.code} has no resolved typed signature")
    result: object = rule.check(
        **{
            rule.subject_parameter: subject,
            rule.context_parameter: ctx,
        }
    )
    if not isinstance(result, list) or any(not isinstance(finding, Finding) for finding in result):
        raise RulesError(f"custom rule {rule.code} must return list[Finding]")
    return result
