"""CLI test command entry point."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.test.execution import (
    execute_test_plan,
    prepare_test_execution,
)
from sqlbuild.cli.commands._helpers.test.invocation import resolve_test_invocation
from sqlbuild.cli.commands._helpers.test.outputs import (
    resolve_test_exit_code,
    write_test_completion_output,
)
from sqlbuild.cli.commands._helpers.test.planning import compile_test_plan
from sqlbuild.cli.commands.models import (
    TestCommandRequest,
    TestExecutionPreparation,
    TestInvocation,
)
from sqlbuild.cli.progress.main._write_execution_header import write_execution_header
from sqlbuild.cli.target_artifacts.main._write_test_runtime_target import write_test_runtime_target
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.testing.models import SqlTestExecutionResult


def run_test(request: TestCommandRequest) -> int:
    """Execute the test command."""

    invocation: TestInvocation = resolve_test_invocation(request=request)
    invocation.progress_stream.write("\n")
    write_execution_header(
        stream=invocation.progress_stream,
        command="sqb test",
        target=None,
        concurrency=1,
        use_color=invocation.use_color,
    )
    pipeline_result: CompilePipelineResult = compile_test_plan(
        request=request,
        invocation=invocation,
    )
    preparation: TestExecutionPreparation = prepare_test_execution(
        invocation=invocation,
        pipeline_result=pipeline_result,
    )
    results: tuple[SqlTestExecutionResult, ...] = execute_test_plan(
        invocation=invocation,
        pipeline_result=pipeline_result,
        preparation=preparation,
    )
    write_test_runtime_target(
        target_dir=invocation.effective_project_dir / "target",
        adapter=invocation.adapter,
        plan_output=pipeline_result.plan_output,
        results=results,
    )
    write_test_completion_output(
        request=request,
        invocation=invocation,
        results=results,
    )
    return resolve_test_exit_code(results)
