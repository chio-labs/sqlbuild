"""Run one project through the mutation script and record every step's outputs."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

from scripts.compiler_differential._helpers.comparing.compare import as_json_object
from scripts.planner_differential._helpers.capturing.canonical import (
    canonical_plan_capture,
    canonical_value,
    mask_console_text,
    mask_text,
)
from scripts.planner_differential._helpers.capturing.state_tables import (
    state_delta,
    state_rows,
)
from scripts.planner_differential._helpers.running.commands import harness_environment, run_sqb
from scripts.planner_differential._helpers.running.snapshot import (
    project_files,
    restore_project_files,
)
from scripts.planner_differential._helpers.steps.arguments import step_arguments
from scripts.planner_differential._helpers.steps.mutations import apply_mutation
from scripts.planner_differential._helpers.steps.targets import plan_models, role_target
from scripts.planner_differential.constants import (
    BUILD_SUMMARY_PREFIXES,
    CAPTURE_DIRECTORY,
    COPY_IGNORED,
    ERROR_LINE_PATTERN,
    PLAN_CAPTURE_ENV_VAR,
    PROJECT_DIRECTORY,
    PROJECT_PATH_MASK,
    WORK_PATH_MASK,
)
from scripts.planner_differential.models import (
    CommandResult,
    ModelFacts,
    MutationResult,
    PlannerProject,
    RunOptions,
    StepContext,
    TextMasks,
)

_SOURCE_MAP_KEY: str = "source_map"
_SELECTION_FLAGS: frozenset[str] = frozenset({"--select", "--exclude"})


def project_slug(name: str) -> str:
    """Return a file name for a project name such as `fixture/orders`."""

    return name.replace("/", "__")


def run_project(*, project: PlannerProject, options: RunOptions) -> dict[str, object]:
    """Build the project once per step after its mutation and return the step records."""

    case_dir: Path = options.work_dir / project_slug(project.name)
    project_dir: Path = _prepared_project(project=project, case_dir=case_dir)
    masks: TextMasks = TextMasks(
        replacements=tuple(
            (str(path), mask)
            for path, mask in (
                (project_dir.resolve(), PROJECT_PATH_MASK),
                (project_dir, PROJECT_PATH_MASK),
                (options.work_dir.resolve(), WORK_PATH_MASK),
                (options.work_dir, WORK_PATH_MASK),
            )
        ),
        today=date.today(),
    )
    environment: dict[str, str] = harness_environment()
    models: tuple[ModelFacts, ...] = ()
    source_tables: tuple[str, ...] = ()
    previous_state: dict[str, list[str]] = {}
    records: list[dict[str, object]] = []
    for index, step in enumerate(options.steps):
        context: StepContext = StepContext(
            project_dir=project_dir,
            models=models,
            source_tables=source_tables,
            environment=environment,
            python=options.python,
        )
        record: dict[str, object] = {"step": step.name}
        records.append(record)
        target: ModelFacts | None = (
            None
            if step.role is None
            else role_target(
                role=step.role, index=step.index, models=models, project_dir=project_dir
            )
        )
        if step.role is not None and target is None:
            record["skipped"] = f"no {step.role} model"
            continue
        arguments: tuple[str, ...] | None = step_arguments(
            step=step, context=context, target=target
        )
        if arguments is None:
            record["skipped"] = "no value for a flag placeholder"
            continue
        saved: dict[str, bytes] = project_files(project_dir)
        if step.mutation is not None and target is not None:
            mutation: MutationResult = apply_mutation(
                name=step.mutation, context=context, target=target
            )
            record["mutation"] = {
                "applied": mutation.applied,
                "note": mask_text(text=mutation.note, masks=masks),
            }
        record["arguments"] = list(arguments)
        capture_dir: Path = case_dir / CAPTURE_DIRECTORY / f"{index:02d}-{step.name}"
        shutil.rmtree(capture_dir, ignore_errors=True)
        plan_json: CommandResult = run_sqb(
            arguments=("plan", "--json", *arguments),
            project_dir=project_dir,
            environment={**environment, PLAN_CAPTURE_ENV_VAR: str(capture_dir)},
            python=options.python,
        )
        record["plan_json"] = _plan_json_record(result=plan_json, masks=masks)
        plan_output: list[object] = _plan_capture(capture_dir=capture_dir, masks=masks)
        record["plan_output"] = plan_output
        plan_text: CommandResult = run_sqb(
            arguments=("plan", *arguments),
            project_dir=project_dir,
            environment=environment,
            python=options.python,
        )
        record["plan_text"] = {
            "exit_code": plan_text.exit_code,
            "lines": mask_console_text(text=plan_text.stdout, masks=masks).splitlines(),
            "diagnostics": _diagnostics(result=plan_text, masks=masks),
        }
        build: CommandResult = run_sqb(
            arguments=("build", *arguments),
            project_dir=project_dir,
            environment=environment,
            python=options.python,
        )
        record["build"] = _build_record(result=build, masks=masks)
        state: dict[str, list[str]] = state_rows(project_dir=project_dir, masks=masks)
        record["state"] = state_delta(before=previous_state, after=state)
        previous_state = state
        if plan_json.exit_code == 0 and not set(arguments) & _SELECTION_FLAGS:
            models = plan_models(plan_json.stdout)
        elif plan_json.exit_code != 0 and step.mutation is not None:
            restore_project_files(project_dir=project_dir, files=saved)
            record["reverted"] = True
        source_tables = _source_tables(plan_output) or source_tables
    if not options.keep_work:
        shutil.rmtree(case_dir, ignore_errors=True)
    return {"project": project.name, "steps": records}


def _prepared_project(*, project: PlannerProject, case_dir: Path) -> Path:
    project_dir: Path = case_dir / PROJECT_DIRECTORY
    shutil.rmtree(case_dir, ignore_errors=True)
    if project.source_dir is not None:
        _ = shutil.copytree(
            project.source_dir, project_dir, ignore=shutil.ignore_patterns(*COPY_IGNORED)
        )
    elif project.writer is not None:
        project_dir.mkdir(parents=True)
        project.writer(project_dir)
    return project_dir


def _plan_json_record(*, result: CommandResult, masks: TextMasks) -> dict[str, object]:
    try:
        document: object = canonical_value(value=json.loads(result.stdout), masks=masks)
    except json.JSONDecodeError:
        document = mask_console_text(text=result.stdout, masks=masks).splitlines()
    return {
        "exit_code": result.exit_code,
        "document": document,
        "diagnostics": _diagnostics(result=result, masks=masks),
    }


def _plan_capture(*, capture_dir: Path, masks: TextMasks) -> list[object]:
    return [
        canonical_plan_capture(text=path.read_text(encoding="utf-8"), masks=masks)
        for path in sorted(capture_dir.glob("*.json"))
    ]


def _build_record(*, result: CommandResult, masks: TextMasks) -> dict[str, object]:
    output: str = mask_console_text(text=result.stdout + result.stderr, masks=masks)
    lines: list[str] = [line.strip() for line in output.splitlines() if line.strip()]
    summary: list[str] = [line for line in lines if line.startswith(BUILD_SUMMARY_PREFIXES)]
    return {
        "exit_code": result.exit_code,
        "summary": summary,
        "diagnostics": sorted({line for line in lines if ERROR_LINE_PATTERN.match(line)}),
        "last_line": lines[-1] if lines and result.exit_code != 0 and not summary else None,
    }


def _diagnostics(*, result: CommandResult, masks: TextMasks) -> list[str]:
    return [
        line.strip()
        for line in mask_console_text(text=result.stderr, masks=masks).splitlines()
        if ERROR_LINE_PATTERN.match(line)
    ]


def _source_tables(plan_output: list[object]) -> tuple[str, ...]:
    """Return the warehouse tables of the last captured plan's non-expression sources."""

    last: dict[str, object] | None = as_json_object(plan_output[-1] if plan_output else None)
    source_map: dict[str, object] | None = as_json_object(
        None if last is None else last.get(_SOURCE_MAP_KEY)
    )
    tables: list[str] = []
    for name, value in sorted((source_map or {}).items()):
        entry: dict[str, object] | None = as_json_object(value)
        if entry is None or entry.get("expression") is not None:
            continue
        table: str = str(entry.get("table") or name)
        schema: object = entry.get("schema")
        tables.append(table if schema is None else f"{schema}.{table}")
    return tuple(tables)
