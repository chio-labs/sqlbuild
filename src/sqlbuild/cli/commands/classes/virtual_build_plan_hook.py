"""Plan-ready hook for virtual build CLI progress and safety checks."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.build_execution.run_context import (
    write_build_run_context,
)
from sqlbuild.cli.commands._helpers.build_planning.full_refresh import (
    enforce_snapshot_full_refresh_policy,
)
from sqlbuild.cli.commands._helpers.compile.target_writer import write_compile_target
from sqlbuild.cli.commands.classes.build_progress_callbacks import BuildProgressCallbacks
from sqlbuild.cli.commands.models import BuildRunContext, VirtualBuildPlanHookConfig
from sqlbuild.cli.output.main.plan import format_plan
from sqlbuild.cli.progress.main._write_execution_header import write_execution_header
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.presentation.models import DisplayOptions
from sqlbuild.virtual.executor.models import VirtualBuildExecutionHooks


class VirtualBuildPlanHook:
    """Render the plan, enforce safety, and expose progress callbacks on plan ready."""

    def __init__(
        self,
        *,
        stream: TextIO,
        project_dir: Path,
        discovered_inputs: DiscoveredProjectInputs,
        adapter: BaseAdapter,
        config: VirtualBuildPlanHookConfig,
    ) -> None:
        self._stream = stream
        self._project_dir = project_dir
        self._discovered_inputs = discovered_inputs
        self._adapter = adapter
        self._full_refresh = config.full_refresh
        self._allow_snapshot_full_refresh = config.allow_snapshot_full_refresh
        self._use_color = config.use_color
        self._verbose = config.verbose
        self._debug = config.debug
        self._json_output = config.json_output
        self._execution_command = config.execution_command
        self._concurrency = config.concurrency
        self._connection_config = config.connection_config
        self._selector_files = config.selector_files
        self._virtual_environment_name = config.virtual_environment_name or "default"
        self._unsuffixed_virtual_environment_name = config.unsuffixed_virtual_environment_name
        self.callbacks: BuildProgressCallbacks | None = None
        self._closed: bool = False

    @property
    def elapsed(self) -> float:
        """Elapsed execution seconds since the plan was rendered."""

        return self.callbacks.elapsed if self.callbacks is not None else 0

    def on_plan_ready(
        self,
        *,
        project: CompiledProject,
        plan_output: PlanOutput,
        python_plan_entries: tuple[PythonPlanEntry, ...],
    ) -> VirtualBuildExecutionHooks:
        """Render the plan and return node progress hooks for execution."""

        plan_text: str = format_plan(
            plan=plan_output,
            full_refresh=self._full_refresh,
            use_color=self._use_color,
            display_options=DisplayOptions(max_entries_per_section=None if self._verbose else 50),
            python_plan_entries=python_plan_entries,
        )
        self._stream.write("\n" + plan_text + "\n\n")
        self._stream.flush()
        enforce_snapshot_full_refresh_policy(
            plan=plan_output,
            snapshots_config=self._discovered_inputs.project_config.snapshots,
            allow_snapshot_full_refresh=self._allow_snapshot_full_refresh,
            input_stream=sys.stdin,
            output_stream=sys.stdout,
        )
        write_compile_target(
            target_dir=self._project_dir / "target",
            adapter=self._adapter,
            plan_output=plan_output,
        )
        callbacks: BuildProgressCallbacks = BuildProgressCallbacks(
            plan=plan_output,
            use_color=self._use_color,
            verbose=self._verbose,
            debug=self._debug or self._json_output,
        )
        self.callbacks = callbacks
        effective_concurrency: int = (
            self._concurrency if self._concurrency is not None else project.settings.concurrency
        )
        if self._verbose or self._debug:
            base_schema: str | None = project.effective_target_schema
            logical_schema: str | None = base_schema
            if (
                base_schema is not None
                and self._unsuffixed_virtual_environment_name != self._virtual_environment_name
            ):
                logical_schema = f"{base_schema}__{self._virtual_environment_name}"
            physical_schema: str | None = (
                f"{base_schema}__sqb_physical" if base_schema is not None else None
            )
            write_build_run_context(
                stream=self._stream,
                context=BuildRunContext(
                    command=f"sqb {self._execution_command}",
                    project=project,
                    plan=plan_output,
                    discovered_inputs=self._discovered_inputs,
                    python_plan_entries=python_plan_entries,
                    connection_config=self._connection_config,
                    concurrency=effective_concurrency,
                    full_refresh=self._full_refresh,
                    selector_files=self._selector_files,
                    virtual_logical_schema=logical_schema,
                    virtual_physical_schema=physical_schema,
                ),
                use_color=self._use_color,
            )
        else:
            write_execution_header(
                stream=self._stream,
                command=f"sqb {self._execution_command}",
                target=None,
                concurrency=effective_concurrency,
                use_color=self._use_color,
            )
        return VirtualBuildExecutionHooks(
            on_node_start=lambda name, resource_kind: callbacks.on_node_start(
                name=name, resource_kind=resource_kind
            ),
            on_node_complete=callbacks.on_node_complete,
            on_sub_progress=callbacks.on_sub_progress,
            on_scheduler_state=(
                callbacks.on_scheduler_state if self._verbose or self._debug else None
            ),
            on_statement_complete=(
                callbacks.on_statement_complete if self._verbose or self._debug else None
            ),
        )

    def close(self) -> None:
        """Close plan callbacks once without changing the build outcome."""

        if self._closed:
            return
        self._closed = True
        if self.callbacks is None:
            return
        try:
            self.callbacks.close()
        except BaseException:
            return
