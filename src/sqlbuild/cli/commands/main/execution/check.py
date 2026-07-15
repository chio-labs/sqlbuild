"""CLI check command entry point for Python checks."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.check.execution import (
    execute_check_plan,
    prepare_check_execution,
)
from sqlbuild.cli.commands._helpers.check.invocation import resolve_check_invocation
from sqlbuild.cli.commands._helpers.check.models import (
    CheckCommandRequest,
    CheckExecutionPreparation,
    CheckInvocation,
)
from sqlbuild.cli.commands._helpers.check.outputs import (
    resolve_check_exit_code,
    write_check_completion_output,
)
from sqlbuild.cli.commands._helpers.check.planning import compile_check_plan
from sqlbuild.cli.progress.main.write_execution_header import write_execution_header
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.python_nodes.models import PythonCheckExecutionResult
from sqlbuild.provider.classes.session import ProviderSession
from sqlbuild.provider.main.session import build_provider_session


def run_check(request: CheckCommandRequest) -> int:
    """Execute the check command."""

    invocation: CheckInvocation = resolve_check_invocation(request=request)
    invocation.progress_stream.write("\n")
    write_execution_header(
        stream=invocation.progress_stream,
        command="sqb check",
        target=None,
        concurrency=1,
        use_color=invocation.use_color,
    )
    pipeline_result: CompilePipelineResult = compile_check_plan(
        request=request,
        invocation=invocation,
    )
    preparation: CheckExecutionPreparation = prepare_check_execution(
        request=request,
        invocation=invocation,
        pipeline_result=pipeline_result,
    )
    provider_session: ProviderSession = build_provider_session(
        discovered_providers=invocation.discovered_inputs.providers
    )
    try:
        results: tuple[PythonCheckExecutionResult, ...] = execute_check_plan(
            invocation=invocation,
            pipeline_result=pipeline_result,
            preparation=preparation,
            providers=provider_session.providers,
        )
        write_check_completion_output(
            request=request,
            invocation=invocation,
            preparation=preparation,
            results=results,
        )
        return resolve_check_exit_code(results)
    finally:
        provider_session.close()
