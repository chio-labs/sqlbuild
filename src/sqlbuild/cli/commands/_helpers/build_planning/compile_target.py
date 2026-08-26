"""Build command compile target writing phase."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.compile.target_writer import write_compile_target
from sqlbuild.cli.commands.models import (
    BuildCommandRequest,
    BuildInvocation,
)
from sqlbuild.compiler.manifest.main.build import build_manifest
from sqlbuild.compiler.pipeline.models import CompilePipelineResult


def write_build_compile_target(
    *,
    request: BuildCommandRequest,
    invocation: BuildInvocation,
    pipeline_result: CompilePipelineResult,
) -> None:
    """Write the compile target artifacts with the optional manifest payload."""

    manifest_payload: dict[str, object] | None = None
    if request.manifest:
        manifest_payload = build_manifest(
            project=pipeline_result.project,
            plan_output=pipeline_result.plan_output,
            project_name=invocation.discovered_inputs.project_config.name,
            adapter_type=invocation.adapter_name,
            upstream_deps=pipeline_result.plan_output.upstream_deps,
            downstream_deps=pipeline_result.plan_output.downstream_deps,
        )
    write_compile_target(
        target_dir=invocation.effective_project_dir / "target",
        adapter=invocation.adapter,
        plan_output=pipeline_result.plan_output,
        manifest=manifest_payload,
    )
