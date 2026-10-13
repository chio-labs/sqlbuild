"""Thread and future handling around one rules run and early SQL lint."""

from __future__ import annotations

from concurrent.futures import Executor, Future, ThreadPoolExecutor
from contextvars import Token
from pathlib import Path
from threading import Event

from sqlbuild._native import run_lint
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledSqlExpansion,
    DeclarationScopeBuild,
    SqlExpansionContext,
)
from sqlbuild.compiler.compile.types import CompileInputsView
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.lint.classes.stop_context import LintStopContext
from sqlbuild.lint.main.build_expansion_context import build_expansion_context
from sqlbuild.lint.models import LintConfig, LintRunResult
from sqlbuild.rule_engine._helpers.engine.custom_dispatch import evaluate_native, start_custom_rules
from sqlbuild.rule_engine._helpers.run.rules import (
    early_lint_expansions,
    finish_rule_run,
    plan_rule_run,
    run_planned_sql_rules,
    sql_lint_preparation,
)
from sqlbuild.rule_engine.models import (
    CustomRulesOutcome,
    PreparedSqlLint,
    PreparedSqlLintResult,
    RuleRunPlan,
    RulesConfig,
    RulesResult,
    RulesRunResult,
    SqlExpansionReuse,
    SqlRulesEvaluation,
)


def evaluate_rules(
    *,
    graph: ProjectGraph,
    discovered_inputs: DiscoveredProjectInputs,
    config: RulesConfig,
    project_dir: Path,
    dialect: str,
    selected_keys: frozenset[CompiledObjectKey] | None = None,
    prepared_sql: PreparedSqlLint | None = None,
    expansion_reuse: SqlExpansionReuse | None = None,
    no_sql_analysis: bool = False,
) -> RulesRunResult:
    """Evaluate independent rule phases concurrently, then finalize their combined findings."""

    plan: RuleRunPlan = plan_rule_run(
        graph=graph,
        config=config,
        project_dir=project_dir,
        selected_keys=selected_keys,
        no_sql_analysis=no_sql_analysis,
    )
    with (
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="sqlbuild-custom-rules") as custom,
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="sqlbuild-rules") as executor,
    ):
        custom_outcome: Future[CustomRulesOutcome] | None = start_custom_rules(
            executor=custom,
            project=plan.project,
            config=plan.config,
            project_dir=plan.project_dir,
            catalogue=plan.catalogue,
            custom_payloads=plan.custom_payloads,
            dialect=dialect,
        )
        native_result: Future[RulesResult] = executor.submit(
            evaluate_native,
            project=plan.project,
            config=plan.config,
            project_dir=plan.project_dir,
            catalogue=plan.catalogue,
            dialect=dialect,
            defer_suppressions=True,
            custom_payloads=plan.custom_payloads,
            custom_outcome=custom_outcome,
        )
        sql_result: SqlRulesEvaluation = run_planned_sql_rules(
            plan=plan,
            graph=graph,
            discovered_inputs=discovered_inputs,
            dialect=dialect,
            prepared_sql=prepared_sql,
            expansion_reuse=expansion_reuse,
        )
        result: RulesResult = native_result.result()
    return finish_rule_run(plan=plan, sql_result=sql_result, result=result)


def prepare_sql_rules(
    *, inputs: CompileInputsView, executor: Executor, dialect: str, stop: Event
) -> PreparedSqlLint | None:
    """Start early SQL lint on `executor` when the project selects SQL rules without a cache."""

    preparation: tuple[Path, tuple[str, ...], LintConfig] | None = sql_lint_preparation(
        inputs=inputs, dialect=dialect
    )
    if preparation is None:
        return None
    project_dir, codes, config = preparation
    return PreparedSqlLint(
        codes=codes,
        project_dir=project_dir,
        future=executor.submit(
            _prepare_sql_lint,
            project_dir=project_dir,
            config=config,
            discovered_inputs=inputs.discovered_inputs,
            static_declaration_scope=inputs.declaration_scope,
            compiled_expansions=early_lint_expansions(inputs.model_inputs),
            stop=stop,
        ),
    )


def _prepare_sql_lint(
    *,
    project_dir: Path,
    config: LintConfig,
    discovered_inputs: DiscoveredProjectInputs,
    static_declaration_scope: DeclarationScopeBuild | None,
    compiled_expansions: dict[Path, CompiledSqlExpansion],
    stop: Event,
) -> PreparedSqlLintResult:
    stop_token: Token[Event | None] = LintStopContext.active.set(stop)
    try:
        context: SqlExpansionContext = build_expansion_context(
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
            static_declaration_scope=static_declaration_scope,
        )
        result: LintRunResult = run_lint(
            project_dir=project_dir,
            config=config,
            discovered_inputs=discovered_inputs,
            compiled_expansions=compiled_expansions,
            expansion_context=context,
        )
    finally:
        LintStopContext.active.reset(stop_token)
    return PreparedSqlLintResult(result=result, context=context)
