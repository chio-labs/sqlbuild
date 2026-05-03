"""Write runtime SQL artifacts to target/run."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.shared.models import LifeCycleEvent
from sqlbuild.adapter.shared.types import LifeCycleEventKind
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.run.models import ModelExecutionResult

_RUN_DIR: str = "run"
_MODELS_DIR: str = "models"


def write_runtime_target(
    *,
    target_dir: Path,
    plan_output: PlanOutput,
    result: BuildExecutionResult,
) -> None:
    """Write executed model lifecycle SQL under target/run."""

    run_dir: Path = target_dir / _RUN_DIR

    model_entry_map: dict[str, ModelPlanEntry] = {
        entry.name: entry for entry in plan_output.model_entries
    }

    model_result: ModelExecutionResult
    for model_result in result.model_results:
        if not model_result.lifecycle_events:
            continue
        sql_events: tuple[LifeCycleEvent, ...] = tuple(
            e for e in model_result.lifecycle_events if e.kind == LifeCycleEventKind.SQL
        )
        if not sql_events:
            continue
        entry: ModelPlanEntry | None = model_entry_map.get(model_result.model_name)
        if entry is None:
            continue
        run_path: Path = run_dir / _model_output_path(entry.relative_path)
        _write_sql(
            path=run_path,
            sql="\n\n".join(_format_statement(e.content) for e in sql_events),
        )


def _write_sql(*, path: Path, sql: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sql.rstrip() + "\n", encoding="utf-8")


def _model_output_path(relative_path: Path) -> Path:
    parts: tuple[str, ...] = relative_path.parts
    if parts and parts[0] == _MODELS_DIR:
        return Path(*parts)
    return Path(_MODELS_DIR) / relative_path


def _format_statement(statement: str) -> str:
    stripped: str = statement.rstrip()
    if not stripped:
        return statement
    if stripped.endswith(";"):
        return stripped
    return f"{stripped};"
