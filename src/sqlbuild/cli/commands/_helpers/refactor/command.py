"""Run `sqb rename` and `sqb mv`: plan from compiler facts, verify, then write."""

from __future__ import annotations

import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from typing import TextIO

from sqlbuild.cli.commands._helpers.refactor.compile_facts import compile_for_refactor
from sqlbuild.cli.commands._helpers.refactor.output import (
    render_refactor_json,
    render_refactor_text,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import RefactorCommandRequest, RefactorCompile
from sqlbuild.cli.commands.types import CliCommand
from sqlbuild.compiler.compile.models import CompilerDiagnostic
from sqlbuild.compiler.refactoring.constants import (
    COLUMN_KIND_PREFIX,
    COLUMN_TARGET_SEPARATOR,
    MODEL_KIND_PREFIX,
)
from sqlbuild.compiler.refactoring.exceptions import RefactorInputError
from sqlbuild.compiler.refactoring.main.commit_refactor_plan import commit_refactor_plan
from sqlbuild.compiler.refactoring.main.plan_column_rename import plan_column_rename
from sqlbuild.compiler.refactoring.main.plan_model_refactor import plan_model_refactor
from sqlbuild.compiler.refactoring.main.stage_refactor_plan import stage_refactor_plan
from sqlbuild.compiler.refactoring.main.with_model_migration import with_model_migration
from sqlbuild.compiler.refactoring.models import RefactorPlan, RefactorRequest
from sqlbuild.compiler.refactoring.types import RefactorOperation, RefactorStatus
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.presentation.main.supports_color import supports_color

_STAGING_PREFIX: str = "sqb-refactor-"


def run_refactor_command(*, request: RefactorCommandRequest) -> int:
    """Plan, verify in a scratch copy, and write one rename or move."""

    project_dir: Path = (request.project_dir or Path.cwd()).resolve()
    stream: TextIO = sys.stderr if request.json_output else sys.stdout
    use_color: bool = not request.no_color and supports_color()
    status: TransientStatusReporter = TransientStatusReporter(stream=stream, use_color=use_color)
    try:
        return _run(request=request, project_dir=project_dir, status=status, use_color=use_color)
    except RefactorInputError as error:
        status.close()
        raise CliUserError(error.message, code=error.code, help=error.help) from error
    finally:
        status.close()


def _run(
    *,
    request: RefactorCommandRequest,
    project_dir: Path,
    status: TransientStatusReporter,
    use_color: bool,
) -> int:
    started: float = time.monotonic()
    status.start("Compiling project...")
    before: RefactorCompile = compile_for_refactor(project_dir=project_dir)
    if before.project is None or before.errors:
        status.error("Project does not compile; fix it before renaming (sqb compile)")
        _write_errors(errors=before.errors)
        return 1
    status.complete(message=f"Compiled project. ({time.monotonic() - started:.2f}s)")
    refactor_request: RefactorRequest = _refactor_request(request=request)
    status.start("Planning edits...")
    plan: RefactorPlan = (
        plan_column_rename(project=before.project, request=refactor_request)
        if refactor_request.operation == RefactorOperation.RENAME_COLUMN
        else plan_model_refactor(project=before.project, request=refactor_request)
    )
    status.complete(message=f"Planned edits to {len(plan.changes)} files.")
    if plan.blocking or plan.manual:
        status.error("Refused: some references cannot be rewritten safely.")
        return _finish(
            request=request,
            plan=plan,
            status=RefactorStatus.REFUSED,
            diagnostics=(),
            use_color=use_color,
        )
    with tempfile.TemporaryDirectory(prefix=_STAGING_PREFIX) as staging:
        staging_dir: Path = Path(staging)
        status.start("Verifying the edited project compiles...")
        originals: dict[str, str] = stage_refactor_plan(
            project_dir=project_dir, staging_dir=staging_dir, plan=plan
        )
        after: RefactorCompile = compile_for_refactor(project_dir=staging_dir, no_cache=True)
        if refactor_request.operation != RefactorOperation.RENAME_COLUMN:
            migrated: RefactorPlan = with_model_migration(
                plan=plan,
                before=before.project.graph.project,
                after=after.project.graph.project if after.project is not None else None,
                originals=originals,
            )
            if migrated.blocking:
                status.error("Refused: the renamed model's history cannot be kept.")
                return _finish(
                    request=request,
                    plan=migrated,
                    status=RefactorStatus.REFUSED,
                    diagnostics=(),
                    use_color=use_color,
                )
            if migrated.migrations != plan.migrations:
                plan = migrated
                originals = stage_refactor_plan(
                    project_dir=project_dir, staging_dir=staging_dir, plan=plan, copy_inputs=False
                )
                after = compile_for_refactor(project_dir=staging_dir, no_cache=True)
        diagnostics: tuple[CompilerDiagnostic, ...] = _relative(
            errors=after.errors, staging_dir=staging_dir
        )
    if diagnostics:
        status.error("Verification failed: the edited project does not compile.")
        return _finish(
            request=request,
            plan=plan,
            status=RefactorStatus.COMPILE_FAILED,
            diagnostics=diagnostics,
            use_color=use_color,
        )
    status.complete(message="Verified: the edited project compiles.")
    if request.dry_run:
        return _finish(
            request=request,
            plan=plan,
            status=RefactorStatus.DRY_RUN,
            diagnostics=(),
            use_color=use_color,
        )
    status.start(f"Writing {len(plan.changes)} files...")
    commit_refactor_plan(project_dir=project_dir, originals=originals, plan=plan)
    status.complete(message=f"Wrote {len(plan.changes)} files.")
    return _finish(
        request=request,
        plan=plan,
        status=RefactorStatus.APPLIED,
        diagnostics=(),
        use_color=use_color,
    )


def _finish(
    *,
    request: RefactorCommandRequest,
    plan: RefactorPlan,
    status: RefactorStatus,
    diagnostics: tuple[CompilerDiagnostic, ...],
    use_color: bool,
) -> int:
    output: str = (
        render_refactor_json(plan=plan, status=status, diagnostics=diagnostics)
        if request.json_output
        else render_refactor_text(
            plan=plan, status=status, diagnostics=diagnostics, use_color=use_color
        )
    )
    _ = sys.stdout.write(output)
    return 0 if status in {RefactorStatus.APPLIED, RefactorStatus.DRY_RUN} else 1


def _refactor_request(*, request: RefactorCommandRequest) -> RefactorRequest:
    target: str = request.target.strip()
    if request.command == CliCommand.MV:
        if not target.startswith(MODEL_KIND_PREFIX):
            raise CliUserError(
                f"sqb mv moves models; got '{target}'",
                code="C954",
                help="write the target as model:<name>",
            )
        return RefactorRequest(
            operation=RefactorOperation.MOVE_MODEL,
            model_name=target.removeprefix(MODEL_KIND_PREFIX),
            new_name="",
            destination=request.destination or "",
        )
    new_name: str = (request.new_name or "").strip()
    if target.startswith(MODEL_KIND_PREFIX):
        if request.cascade:
            raise CliUserError("--cascade applies to column renames only", code="C954")
        return RefactorRequest(
            operation=RefactorOperation.RENAME_MODEL,
            model_name=target.removeprefix(MODEL_KIND_PREFIX),
            new_name=new_name,
        )
    if target.startswith(COLUMN_KIND_PREFIX) and COLUMN_TARGET_SEPARATOR in target:
        model_name: str
        column_name: str
        model_name, column_name = target.removeprefix(COLUMN_KIND_PREFIX).rsplit(
            COLUMN_TARGET_SEPARATOR, 1
        )
        return RefactorRequest(
            operation=RefactorOperation.RENAME_COLUMN,
            model_name=model_name,
            column_name=column_name,
            new_name=new_name,
            cascade=request.cascade,
        )
    raise CliUserError(
        f"cannot rename '{target}'",
        code="C954",
        help="write the target as model:<name> or column:<model>.<column>",
    )


def _relative(
    *, errors: tuple[CompilerDiagnostic, ...], staging_dir: Path
) -> tuple[CompilerDiagnostic, ...]:
    return tuple(
        replace(error, path=error.path.relative_to(staging_dir))
        if error.path is not None
        and error.path.is_absolute()
        and error.path.is_relative_to(staging_dir)
        else error
        for error in errors
    )


def _write_errors(*, errors: tuple[CompilerDiagnostic, ...]) -> None:
    error: CompilerDiagnostic
    for error in errors:
        location: str = f"{error.path.as_posix()}: " if error.path is not None else ""
        print(f"error[{error.code}] {location}{error.message}", file=sys.stderr)
