"""Virtual mode delegation for the seed command."""

from __future__ import annotations

from sqlbuild.cli.commands.helpers.build.models import VirtualBuildCliRequest
from sqlbuild.cli.commands.helpers.planning.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.helpers.seed.models import SeedCommandRequest, SeedInvocation
from sqlbuild.cli.commands.main.commands.virtual_build import run_virtual_build
from sqlbuild.provider.classes.session import ProviderSession
from sqlbuild.provider.main.session import build_provider_session


def execute_virtual_seed(*, request: SeedCommandRequest, invocation: SeedInvocation) -> int:
    """Delegate seed-only virtual mode execution to virtual build."""

    provider_session: ProviderSession = build_provider_session(
        discovered_providers=invocation.discovered_inputs.providers
    )
    try:
        return run_virtual_build(
            project_dir=invocation.effective_project_dir,
            discovered_inputs=invocation.discovered_inputs,
            adapter=invocation.adapter,
            adapter_name=invocation.adapter_name,
            connection_config=invocation.connection_config,
            request=VirtualBuildCliRequest(
                selected_target=request.selected_target,
                include_python=False,
                seed_only=True,
                select=request.select,
                exclude=request.exclude,
                concurrency=request.concurrency,
                cli_vars=request.cli_vars,
                json_output=request.json_output,
                json_output_path=request.json_output_path,
                execution_command="seed",
                use_color=invocation.use_color,
                external_sql_reference_resolver=resolve_external_sql_reference_resolver(
                    project_dir=invocation.effective_project_dir,
                    discovered_inputs=invocation.discovered_inputs,
                ),
                providers=provider_session.providers,
            ),
        )
    finally:
        provider_session.close()
