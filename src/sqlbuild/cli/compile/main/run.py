"""Public compile command entrypoint."""

from __future__ import annotations

from sqlbuild.cli.compile_reuse.main._attempt_compile_reuse import attempt_compile_reuse
from sqlbuild.cli.compile_reuse.models import CompileReuseAttempt, CompileReuseRequest
from sqlbuild.cli.compile_reuse.types import CompileReuseOutcome
from sqlbuild.cli.entry.models import CompileCommandRequest, CompileProfileFlags


def run_compile(request: CompileCommandRequest) -> int:
    """Run one compile command request, replaying the previous compile when nothing changed."""

    attempt: CompileReuseAttempt = attempt_compile_reuse(request=_reuse_request(request=request))
    if attempt.outcome is CompileReuseOutcome.HIT and attempt.exit_code is not None:
        return attempt.exit_code
    from sqlbuild.cli.commands.main.project._compile import run_compile as run_full_compile

    return run_full_compile(request=request, reuse_attempt=attempt)


def _reuse_request(*, request: CompileCommandRequest) -> CompileReuseRequest:
    flags: CompileProfileFlags = request.profile_flags
    return CompileReuseRequest(
        project_dir=request.project_dir,
        selected_target=request.selected_target,
        json_output=request.json_output,
        no_color=request.no_color,
        manifest=request.manifest,
        dag_path=request.dag_path,
        defer_to=request.defer_to,
        no_cache=request.no_cache,
        no_sql_validation=request.no_sql_validation,
        lineage_mode=str(request.lineage_mode.value),
        select=request.select,
        exclude=request.exclude,
        cli_vars=request.cli_vars,
        debug=request.debug,
        profiling=(
            flags.skip_discovery_sql_analysis
            or flags.skip_column_inference
            or flags.skip_contracts
            or flags.skip_write
        ),
    )
