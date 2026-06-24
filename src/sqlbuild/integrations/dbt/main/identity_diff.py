"""Public dbt identity-diff entrypoint."""

from __future__ import annotations

import argparse
import json
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

    identity_args: DbtIdentityDiffArgs = _parse_identity_diff_args(args=args)
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    dbt_options: DbtCliOptions = resolve_dbt_plan_options(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        dbt_args=(),
    )
    runner: DbtRunner = DbtRunner()

    if on_progress is not None:
        on_progress("Compiling current dbt project...")
    compile_result: DbtCommandResult = runner.compile(options=dbt_options)
    if compile_result.returncode != 0:
        raise DbtInteropRuntimeError(
            "dbt compile failed for identity-diff",
            help=compile_result.stderr or compile_result.stdout,
        )
    if on_progress is not None:
        on_progress("Compiled current dbt project.")

    current_manifest: DbtManifestIndex = load_dbt_manifest_index(
        manifest_path=resolve_dbt_manifest_path(options=dbt_options)
    )
    selected_unique_ids: tuple[str, ...] = _selected_model_unique_ids(
        runner=runner,
        dbt_options=dbt_options,
        select=identity_args.select,
        exclude=identity_args.exclude,
        current_manifest=current_manifest,
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
    if on_progress is not None:
        on_progress(f"Compiling dbt identity ref '{against}'...")
    try:
        ref_compile: DbtReuseFromCompileResult = compile_reuse_from_manifest(
            sqlbuild_project_dir=project_dir,
            dbt_options=dbt_options,
            reuse_from=reuse_from,
            runner=runner,
        )
    except DbtReuseUnavailableError as error:
        raise DbtInteropRuntimeError(str(error), help=error.help) from error
    if on_progress is not None:
        on_progress(f"Compiled dbt identity ref '{against}'.")
    ref_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=json.loads(ref_compile.manifest_contents)
    )

    result: DbtIdentityDiffResult = build_dbt_identity_diff_result(
        current_manifest=current_manifest,
        ref_manifest=ref_manifest,
        selected_unique_ids=selected_unique_ids,
        against=against,
        depth=identity_args.depth,
        full_diff=identity_args.full_diff,
        on_progress=on_progress,
    )
    if identity_args.json_output:
        return format_dbt_identity_diff_json(result)
    return render_dbt_identity_diff_result(
        result=result,
        quiet=identity_args.quiet,
        use_color=use_color,
    )


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


def _parse_identity_diff_args(*, args: tuple[str, ...]) -> DbtIdentityDiffArgs:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(prog="sqb dbt identity-diff")
    parser.add_argument("--select", action="append", default=[])
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--against", default=None)
    parser.add_argument("--quiet", action="store_true", default=False)
    parser.add_argument("--depth", type=int, default=None)
    parser.add_argument("--full-diff", action="store_true", default=False)
    parser.add_argument("--json", dest="json_output", action="store_true", default=False)
    parsed: argparse.Namespace = parser.parse_args(args)
    return DbtIdentityDiffArgs(
        select=tuple(parsed.select),
        exclude=tuple(parsed.exclude),
        against=parsed.against,
        quiet=parsed.quiet,
        depth=parsed.depth,
        json_output=parsed.json_output,
        full_diff=parsed.full_diff,
    )
