"""CLI audit command entry point."""

from __future__ import annotations

from sqlbuild.cli.commands.helpers.audit.execution import (
    execute_audit_plan,
    prepare_audit_execution,
)
from sqlbuild.cli.commands.helpers.audit.invocation import resolve_audit_invocation
from sqlbuild.cli.commands.helpers.audit.models import (
    AuditCommandRequest,
    AuditExecutionPreparation,
    AuditInvocation,
)
from sqlbuild.cli.commands.helpers.audit.outputs import (
    resolve_audit_exit_code,
    write_audit_completion_output,
)
from sqlbuild.cli.commands.helpers.audit.planning import compile_audit_plan
from sqlbuild.cli.progress.main.write_execution_header import write_execution_header
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.auditing.models import AuditExecutionResult


def run_audit(request: AuditCommandRequest) -> int:
    """Execute the audit command."""

    invocation: AuditInvocation = resolve_audit_invocation(request=request)
    invocation.progress_stream.write("\n")
    write_execution_header(
        stream=invocation.progress_stream,
        command="sqb audit",
        target=None,
        concurrency=1,
        use_color=invocation.use_color,
    )
    pipeline_result: CompilePipelineResult = compile_audit_plan(
        request=request,
        invocation=invocation,
    )
    preparation: AuditExecutionPreparation = prepare_audit_execution(
        invocation=invocation,
        pipeline_result=pipeline_result,
    )
    results: tuple[AuditExecutionResult, ...] = execute_audit_plan(
        invocation=invocation,
        pipeline_result=pipeline_result,
        preparation=preparation,
    )
    write_audit_completion_output(
        request=request,
        invocation=invocation,
        results=results,
    )
    return resolve_audit_exit_code(results)
