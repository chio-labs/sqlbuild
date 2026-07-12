"""Load command execution preparation phase."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.helpers.load.models import (
    LoadCommandRequest,
    LoadExecutionPreparation,
    LoadInvocation,
)
from sqlbuild.cli.commands.helpers.load.references import validate_reference_source_targets
from sqlbuild.cli.commands.shared.helpers.config.adapters import resolve_adapter
from sqlbuild.cli.commands.shared.helpers.connection.core import (
    resolve_project_connection_config,
)
from sqlbuild.compiler.compile.main.effective_runtime import build_effective_runtime_config
from sqlbuild.compiler.compile.main.effective_settings import build_effective_settings_config
from sqlbuild.compiler.planner.models import CursorOverrides
from sqlbuild.provider.main.session import build_provider_session
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def prepare_load_execution(
    *, request: LoadCommandRequest, invocation: LoadInvocation
) -> LoadExecutionPreparation:
    """Prepare adapter, connection, runtime, concurrency, and providers for load."""

    adapter_name: str = resolve_effective_adapter_name(
        project_config=invocation.discovered_inputs.project_config,
        local_config=invocation.discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name=adapter_name,
        project_dir=invocation.effective_project_dir,
    )
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=invocation.discovered_inputs,
        project_dir=invocation.effective_project_dir,
        selected_target=request.selected_target,
        cli_vars=request.cli_vars,
    )
    validate_reference_source_targets(
        adapter=adapter,
        connection_config=connection_config,
        selected_sources=invocation.selected_sources,
        reference_sources=invocation.reference_sources,
    )
    target_name: str | None
    effective_vars: dict[str, object]
    run_id: str
    target_name, effective_vars, run_id = build_effective_runtime_config(
        discovered_inputs=invocation.discovered_inputs,
        selected_target=request.selected_target,
        cli_vars=request.cli_vars,
    )
    effective_concurrency: int = max(
        1,
        request.concurrency
        if request.concurrency is not None
        else build_effective_settings_config(
            discovered_inputs=invocation.discovered_inputs
        ).concurrency,
    )
    return LoadExecutionPreparation(
        adapter_name=adapter_name,
        adapter=adapter,
        connection_config=connection_config,
        target_name=target_name,
        effective_vars=effective_vars,
        run_id=run_id,
        effective_cursor_overrides=request.cursor_overrides or CursorOverrides(),
        effective_concurrency=effective_concurrency,
        provider_session=build_provider_session(
            discovered_providers=invocation.discovered_inputs.providers
        ),
    )
