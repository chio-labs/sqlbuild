"""Public dbt identity-diff entrypoint."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.exceptions import (
    DbtInteropRuntimeError,
    DbtReuseUnavailableError,
)
from sqlbuild.integrations.dbt.helpers.cli.runner import DbtRunner
from sqlbuild.integrations.dbt.helpers.identity_diff.args import parse_dbt_identity_diff_args
from sqlbuild.integrations.dbt.helpers.identity_diff.core import (
    build_dbt_identity_diff_result,
    format_dbt_identity_diff_json,
    render_dbt_identity_diff_result,
)
from sqlbuild.integrations.dbt.helpers.manifest.core import (
    build_dbt_manifest_index,
    load_dbt_manifest_index,
)
from sqlbuild.integrations.dbt.helpers.planning.runtime import (
    resolve_dbt_manifest_path,
    resolve_dbt_plan_options,
)
from sqlbuild.integrations.dbt.helpers.reuse.reuse_from import compile_reuse_from_manifest
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCommandResult,
    DbtIdentityDiffArgs,
    DbtIdentityDiffResult,
    DbtLsResult,
    DbtReuseFromCompileResult,
)
from sqlbuild.spec.models.project import DbtReuseFromConfig


def build_dbt_identity_diff_output(
    *,
    project_dir: Path,
    args: tuple[str, ...],
    use_color: bool,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    """Build formatted dbt identity-diff output."""

    identity_args: DbtIdentityDiffArgs = _timed_phase(
        on_progress=on_progress,
        start_message="Parsing identity-diff arguments...",
        complete_message="Parsed identity-diff arguments.",
        operation=lambda: parse_dbt_identity_diff_args(args=args),
    )
    discovered_inputs: DiscoveredProjectInputs = _timed_phase(
        on_progress=on_progress,
        start_message="Inspecting project configuration...",
        complete_message="Inspected project configuration.",
        operation=lambda: discover_project_inputs(project_dir=project_dir),
    )
    dbt_options: DbtCliOptions = _timed_phase(
        on_progress=on_progress,
        start_message="Resolving dbt identity-diff options...",
        complete_message="Resolved dbt identity-diff options.",
        operation=lambda: resolve_dbt_plan_options(
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
            dbt_args=(),
        ),
    )
    runner: DbtRunner = DbtRunner()

    compile_result: DbtCommandResult = _timed_phase(
        on_progress=on_progress,
        start_message="Compiling current dbt project...",
        complete_message="Compiled current dbt project.",
        operation=lambda: runner.compile(options=dbt_options),
    )
    if compile_result.returncode != 0:
        raise DbtInteropRuntimeError(
            "dbt compile failed for identity-diff",
            help=compile_result.stderr or compile_result.stdout,
        )

    current_manifest: DbtManifestIndex = _timed_phase(
        on_progress=on_progress,
        start_message="Loading current dbt manifest...",
        complete_message="Loaded current dbt manifest.",
        operation=lambda: load_dbt_manifest_index(
            manifest_path=resolve_dbt_manifest_path(options=dbt_options)
        ),
    )
    selected_unique_ids: tuple[str, ...] = _timed_phase(
        on_progress=on_progress,
        start_message="Resolving dbt identity-diff selection...",
        complete_message="Resolved dbt identity-diff selection.",
        operation=lambda: _selected_model_unique_ids(
            runner=runner,
            dbt_options=dbt_options,
            select=identity_args.select,
            exclude=identity_args.exclude,
            current_manifest=current_manifest,
        ),
    )
    if not selected_unique_ids:
        raise DbtInteropRuntimeError("identity-diff selected no dbt models")

    against: str = (
        identity_args.against or discovered_inputs.project_config.dbt.reuse_from.git_ref or ""
    )
    if not against:
        raise DbtInteropRuntimeError(
            "identity-diff requires --against when [dbt.reuse_from].git_ref is not configured"
        )
    reuse_from: DbtReuseFromConfig = replace(
        discovered_inputs.project_config.dbt.reuse_from,
        git_ref=against,
    )
    try:
        ref_compile: DbtReuseFromCompileResult = _timed_phase(
            on_progress=on_progress,
            start_message=f"Compiling dbt identity ref '{against}'...",
            complete_message=f"Compiled dbt identity ref '{against}'.",
            operation=lambda: compile_reuse_from_manifest(
                sqlbuild_project_dir=project_dir,
                dbt_options=dbt_options,
                reuse_from=reuse_from,
                runner=runner,
            ),
        )
    except DbtReuseUnavailableError as error:
        raise DbtInteropRuntimeError(str(error), help=error.help) from error
    ref_manifest: DbtManifestIndex = _timed_phase(
        on_progress=on_progress,
        start_message="Indexing dbt identity ref manifest...",
        complete_message="Indexed dbt identity ref manifest.",
        operation=lambda: build_dbt_manifest_index(
            raw_data=json.loads(ref_compile.manifest_contents)
        ),
    )

    result: DbtIdentityDiffResult = _timed_phase(
        on_progress=on_progress,
        start_message="Building dbt identity diff...",
        complete_message="Built dbt identity diff.",
        operation=lambda: build_dbt_identity_diff_result(
            current_manifest=current_manifest,
            ref_manifest=ref_manifest,
            selected_unique_ids=selected_unique_ids,
            against=against,
            show_paths=identity_args.show_paths,
            max_diff_lines=identity_args.max_diff_lines,
            max_diff_bytes=identity_args.max_diff_bytes,
            on_progress=on_progress,
        ),
    )
    if identity_args.json_output:
        return _timed_phase(
            on_progress=on_progress,
            start_message="Rendering dbt identity diff JSON...",
            complete_message="Rendered dbt identity diff JSON.",
            operation=lambda: format_dbt_identity_diff_json(result),
        )
    return _timed_phase(
        on_progress=on_progress,
        start_message="Rendering dbt identity diff output...",
        complete_message="Rendered dbt identity diff output.",
        operation=lambda: render_dbt_identity_diff_result(
            result=result,
            quiet=identity_args.quiet,
            show_inherited=identity_args.show_inherited,
            show_paths=identity_args.show_paths,
            use_color=use_color,
        ),
    )


def _timed_phase[T](
    *,
    on_progress: Callable[[str], None] | None,
    start_message: str,
    complete_message: str,
    operation: Callable[[], T],
) -> T:
    start: float = time.monotonic()
    if on_progress is not None:
        on_progress(start_message)
    result: T = operation()
    if on_progress is not None:
        on_progress(f"{complete_message} ({time.monotonic() - start:.2f}s)")
    return result


def _selected_model_unique_ids(
    *,
    runner: DbtRunner,
    dbt_options: DbtCliOptions,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    current_manifest: DbtManifestIndex,
) -> tuple[str, ...]:
    if not select and not exclude:
        return tuple(sorted(current_manifest.models_by_unique_id))
    result: DbtLsResult = runner.ls(
        options=dbt_options,
        select=select,
        exclude=exclude,
        resource_types=("model",),
    )
    if result.command.returncode != 0:
        raise DbtInteropRuntimeError(
            "dbt ls failed for identity-diff selection",
            help=result.command.stderr or result.command.stdout,
        )
    return tuple(
        node.unique_id
        for node in result.nodes
        if node.unique_id in current_manifest.models_by_unique_id
    )
