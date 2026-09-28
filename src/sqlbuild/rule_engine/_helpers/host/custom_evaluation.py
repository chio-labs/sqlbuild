"""Isolated Python host for selected repository-defined rules."""

from __future__ import annotations

from collections import Counter
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.rule_engine.classes.project_tree import public_model
from sqlbuild.rule_engine.classes.rule_context import (
    EvaluationRuleContext,
    RuleFactViews,
    build_rule_fact_views,
)
from sqlbuild.rule_engine.classes.runtime_guard import RuntimeGuard
from sqlbuild.rule_engine.exceptions import NonHermeticRuleError, RulesError
from sqlbuild.rule_engine.models import Finding, Model, Project, Rule, RulesConfig
from sqlbuild.rule_engine.types import RuleSubject

type _FindingKey = tuple[str, str, int, int, str, str]


def evaluate_custom_rules(
    *,
    project: CompiledProject,
    config: RulesConfig,
    project_dir: Path,
    selected_rules: tuple[Rule, ...],
    dialect: str = "generic",
    selected_model_paths: frozenset[str] | None = None,
    verify_determinism: bool = False,
    guard: RuntimeGuard | None = None,
) -> list[Finding]:
    """Run only selected custom rules through the Python authoring API."""

    custom_rules: tuple[Rule, ...] = tuple(rule for rule in selected_rules if rule.custom)
    if not custom_rules:
        return []
    models: tuple[CompiledModel, ...] = tuple(
        model
        for model in sorted(project.models, key=lambda item: item.relative_path.as_posix())
        if selected_model_paths is None or model.relative_path.as_posix() in selected_model_paths
    )
    facts: RuleFactViews = build_rule_fact_views(
        project=project, project_dir=project_dir, dialect=dialect
    )

    def run_pass(*, rules: tuple[Rule, ...], subjects: tuple[CompiledModel, ...]) -> list[Finding]:
        return _evaluate_pass(
            project=project,
            config=config,
            project_dir=project_dir,
            selected_rules=selected_rules,
            dialect=dialect,
            facts=facts,
            rules=rules,
            models=subjects,
            guard=guard,
        )

    findings: list[Finding] = run_pass(rules=custom_rules, subjects=models)
    if verify_determinism:
        repeated: list[Finding] = run_pass(rules=custom_rules[::-1], subjects=models[::-1])
        _verify_repeatable(rules=custom_rules, first=findings, repeated=repeated)
    return findings


def _evaluate_pass(
    *,
    project: CompiledProject,
    config: RulesConfig,
    project_dir: Path,
    selected_rules: tuple[Rule, ...],
    dialect: str,
    facts: RuleFactViews,
    rules: tuple[Rule, ...],
    models: tuple[CompiledModel, ...],
    guard: RuntimeGuard | None,
) -> list[Finding]:
    findings: list[Finding] = []
    project_rules: tuple[Rule, ...] = tuple(
        rule for rule in rules if rule.subject is RuleSubject.PROJECT
    )
    model_rules: tuple[Rule, ...] = tuple(
        rule for rule in rules if rule.subject is RuleSubject.MODEL
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
                    guard=guard,
                )
            )
        except NonHermeticRuleError:
            raise
        except Exception as error:
            raise RulesError(f"rule {rule.code} failed for the project: {error}") from error
    for model in models:
        subject: Model = public_model(model)
        for rule, ctx in model_contexts:
            try:
                findings.extend(_invoke(rule=rule, subject=subject, ctx=ctx, guard=guard))
            except NonHermeticRuleError:
                raise
            except Exception as error:
                raise RulesError(
                    f"rule {rule.code} failed for {model.relative_path}: {error}"
                ) from error
    return findings


def _invoke(
    *, rule: Rule, subject: object, ctx: EvaluationRuleContext, guard: RuntimeGuard | None
) -> list[Finding]:
    if rule.subject_parameter is None or rule.context_parameter is None:
        raise RulesError(f"custom rule {rule.code} has no resolved typed signature")
    scope: AbstractContextManager[None] = nullcontext() if guard is None else guard.rule(rule.code)
    with scope:
        result: object = rule.check(
            **{
                rule.subject_parameter: subject,
                rule.context_parameter: ctx,
            }
        )
    if not isinstance(result, list) or any(not isinstance(finding, Finding) for finding in result):
        raise RulesError(f"custom rule {rule.code} must return list[Finding]")
    return result


def _verify_repeatable(
    *, rules: tuple[Rule, ...], first: list[Finding], repeated: list[Finding]
) -> None:
    for rule in rules:
        before: Counter[_FindingKey] = _finding_keys(findings=first, code=rule.code)
        after: Counter[_FindingKey] = _finding_keys(findings=repeated, code=rule.code)
        if before != after:
            raise RulesError(
                f"custom rule {rule.code} is not deterministic: evaluating every subject again "
                f"after the others changed its findings from {before.total()} to "
                f"{after.total()}; keep per-subject results independent of module-level state "
                "and evaluation order"
            )


def _finding_keys(*, findings: list[Finding], code: str) -> Counter[_FindingKey]:
    return Counter(
        (
            finding.code,
            finding.path.as_posix(),
            finding.line,
            finding.column,
            finding.message,
            finding.remediation,
        )
        for finding in findings
        if finding.code == code
    )
