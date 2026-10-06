"""Shared local DuckDB scenario replay execution."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.scenario_output.result_output import complete_scenario_run
from sqlbuild.cli.commands._helpers.scenario_output.run_presentation import (
    begin_scenario_run,
    finish_scenario_run,
)
from sqlbuild.cli.commands.models import ScenarioRunOutputContext, ScenarioRunPresentation
from sqlbuild.compiler.compile.models import CompiledSqlScenario
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.pipeline.main.run import run_scenario_local_test_pipeline
from sqlbuild.executor.scenario.models import ScenarioLocalReplaySource, ScenarioRunResult
from sqlbuild.executor.scenario.types import ScenarioLocalRunStatus


def run_local_scenarios(
    *,
    project_dir: Path,
    pipeline_result: CompilePipelineResult,
    scenarios: tuple[CompiledSqlScenario, ...],
    adapter: BaseAdapter,
    project_name: str,
    strict: bool,
    replay_source: ScenarioLocalReplaySource,
    target_dir: Path,
    output_context: ScenarioRunOutputContext,
) -> int:
    """Replay selected scenarios on run-scoped DuckDB and render results."""

    presentation: ScenarioRunPresentation = begin_scenario_run(
        context=output_context, scenario_count=len(scenarios)
    )
    results: tuple[ScenarioRunResult, ...] = run_scenario_local_test_pipeline(
        project_dir=project_dir,
        pipeline_result=pipeline_result,
        scenarios=scenarios,
        adapter=adapter,
        project_name=project_name,
        strict=strict,
        replay_source=replay_source,
        on_scenario_start=lambda _scenario: (
            presentation.scenario_status.start(presentation.activity)
            if presentation.status_is_tty
            else None
        ),
        on_scenario_complete=lambda _scenario, scenario_plan, result: complete_scenario_run(
            scenario_status=presentation.scenario_status,
            status_is_tty=presentation.status_is_tty,
            target_dir=target_dir,
            adapter=adapter,
            scenario_plan=scenario_plan,
            result=result,
            progress_stream=output_context.progress_stream,
            use_color=output_context.use_color,
        ),
    )
    counts: Counter[ScenarioLocalRunStatus | None] = Counter(
        result.local_status for result in results
    )
    succeeded: bool = (
        counts[ScenarioLocalRunStatus.FAIL] == 0 and counts[ScenarioLocalRunStatus.ERROR] == 0
    )
    finish_scenario_run(
        context=output_context,
        presentation=presentation,
        results=results,
        counts=(
            ("PASS", counts[ScenarioLocalRunStatus.PASS]),
            ("FAIL", counts[ScenarioLocalRunStatus.FAIL]),
            ("ERROR", counts[ScenarioLocalRunStatus.ERROR]),
            ("SKIP", counts[ScenarioLocalRunStatus.SKIP]),
            ("TOTAL", len(results)),
        ),
        succeeded=succeeded,
        local=True,
    )
    return 0 if succeeded else 1
