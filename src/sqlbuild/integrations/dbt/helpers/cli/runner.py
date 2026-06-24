"""dbt CLI runner and `dbt ls` parser."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from sqlbuild.integrations.dbt.exceptions import DbtInteropRuntimeError
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCommandResult,
    DbtLsNode,
    DbtLsResult,
)
from sqlbuild.integrations.dbt.shared.helpers.executable import resolve_dbt_executable
from sqlbuild.integrations.dbt.types import DbtInvoker


def build_dbt_compile_argv(
    *, dbt_executable: str, options: DbtCliOptions, full_refresh: bool = False
) -> tuple[str, ...]:
    """Build argv for dbt compile."""

    argv: tuple[str, ...] = _append_common_options((dbt_executable, "compile"), options=options)
    if full_refresh:
        argv = (*argv, "--full-refresh")
    return argv


def build_dbt_deps_argv(*, dbt_executable: str, options: DbtCliOptions) -> tuple[str, ...]:
    """Build argv for dbt deps."""

    argv: tuple[str, ...] = (dbt_executable, "deps")
    if options.project_dir is not None:
        argv = (*argv, "--project-dir", str(options.project_dir))
    if options.profiles_dir is not None:
        argv = (*argv, "--profiles-dir", str(options.profiles_dir))
    if options.target is not None:
        argv = (*argv, "--target", options.target)
    if options.vars is not None:
        argv = (*argv, "--vars", options.vars)
    return argv


def build_dbt_debug_argv(
    *, dbt_executable: str, options: DbtCliOptions, args: Sequence[str] = ()
) -> tuple[str, ...]:
    """Build argv for dbt debug."""

    return (*_append_common_options((dbt_executable, "debug"), options=options), *args)


def build_dbt_command_argv(
    *,
    dbt_executable: str,
    command: str,
    options: DbtCliOptions,
    args: Sequence[str] = (),
) -> tuple[str, ...]:
    """Build argv for an executable dbt command with resolved common options."""

    return (*_append_common_options((dbt_executable, command), options=options), *args)


def build_dbt_ls_argv(
    *,
    dbt_executable: str,
    options: DbtCliOptions,
    select: Sequence[str] = (),
    exclude: Sequence[str] = (),
    resource_types: Sequence[str] = (),
) -> tuple[str, ...]:
    """Build argv for dbt ls with JSON output."""

    argv: tuple[str, ...] = _append_common_options(
        (dbt_executable, "ls", "--output", "json"), options=options
    )
    value: str
    if select:
        argv = (*argv, "--select", *select)
    if exclude:
        argv = (*argv, "--exclude", *exclude)
    for value in resource_types:
        argv = (*argv, "--resource-type", value)
    return argv


def parse_dbt_ls_json_lines(*, stdout: str) -> tuple[DbtLsNode, ...]:
    """Parse dbt ls JSON-lines output, ignoring non-JSON log lines."""

    nodes: list[DbtLsNode] = []
    line: str
    for line in stdout.splitlines():
        stripped: str = line.strip()
        if not stripped or not stripped.startswith("{"):
            continue
        try:
            payload: object = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        unique_id: object | None = payload.get("unique_id")
        if not isinstance(unique_id, str) or not unique_id:
            continue
        nodes.append(
            DbtLsNode(
                unique_id=unique_id,
                resource_type=_optional_str(payload.get("resource_type")),
                package_name=_optional_str(payload.get("package_name")),
                name=_optional_str(payload.get("name")),
                fqn=_parse_fqn(payload.get("fqn")),
                original_file_path=_optional_str(payload.get("original_file_path")),
                payload=dict(payload),
            )
        )
    return tuple(nodes)


class DbtRunner:
    """Small dbt CLI runner with per-invocation dbt ls memoization."""

    def __init__(
        self, *, dbt_executable: str | None = None, invoker: DbtInvoker | None = None
    ) -> None:
        self.dbt_executable = dbt_executable or resolve_dbt_executable()
        self.invoker = invoker
        self._ls_cache: dict[tuple[str, ...], DbtLsResult] = {}

    def compile(self, *, options: DbtCliOptions, full_refresh: bool = False) -> DbtCommandResult:
        """Run dbt compile."""

        argv: tuple[str, ...] = build_dbt_compile_argv(
            dbt_executable=self.dbt_executable, options=options, full_refresh=full_refresh
        )
        return self._invoke(argv=argv, cwd=options.project_dir)

    def deps(self, *, options: DbtCliOptions) -> DbtCommandResult:
        """Run dbt deps."""

        argv: tuple[str, ...] = build_dbt_deps_argv(
            dbt_executable=self.dbt_executable,
            options=options,
        )
        return self._invoke(argv=argv, cwd=options.project_dir)

    def debug(self, *, options: DbtCliOptions, args: Sequence[str] = ()) -> DbtCommandResult:
        """Run dbt debug."""

        argv: tuple[str, ...] = build_dbt_debug_argv(
            dbt_executable=self.dbt_executable, options=options, args=args
        )
        return self._invoke(argv=argv, cwd=options.project_dir)

    def ls(
        self,
        *,
        options: DbtCliOptions,
        select: Sequence[str] = (),
        exclude: Sequence[str] = (),
        resource_types: Sequence[str] = (),
    ) -> DbtLsResult:
        """Run dbt ls and parse selected nodes."""

        argv: tuple[str, ...] = build_dbt_ls_argv(
            dbt_executable=self.dbt_executable,
            options=options,
            select=select,
            exclude=exclude,
            resource_types=resource_types,
        )
        cached: DbtLsResult | None = self._ls_cache.get(argv)
        if cached is not None:
            return cached
        command: DbtCommandResult = self._invoke(argv=argv, cwd=options.project_dir)
        result: DbtLsResult = DbtLsResult(
            nodes=parse_dbt_ls_json_lines(stdout=command.stdout), command=command
        )
        self._ls_cache[argv] = result
        return result

    def _invoke(self, *, argv: tuple[str, ...], cwd: Path | None) -> DbtCommandResult:
        invoker: DbtInvoker = self.invoker if self.invoker is not None else _subprocess_invoker
        return cast(DbtCommandResult, invoker(argv, cwd))

    def invoke(self, *, argv: tuple[str, ...], cwd: Path | None) -> DbtCommandResult:
        """Run an explicit dbt argv."""

        return self._invoke(argv=argv, cwd=cwd)


def _append_common_options(argv: tuple[str, ...], *, options: DbtCliOptions) -> tuple[str, ...]:
    if options.project_dir is not None:
        argv = (*argv, "--project-dir", str(options.project_dir))
    if options.profiles_dir is not None:
        argv = (*argv, "--profiles-dir", str(options.profiles_dir))
    if options.target is not None:
        argv = (*argv, "--target", options.target)
    if options.target_path is not None:
        argv = (*argv, "--target-path", str(options.target_path))
    if options.vars is not None:
        argv = (*argv, "--vars", options.vars)
    if options.state is not None:
        argv = (*argv, "--state", str(options.state))
    if options.defer:
        argv = (*argv, "--defer")
    return argv


def _subprocess_invoker(argv: tuple[str, ...], cwd: Path | None) -> DbtCommandResult:
    try:
        completed: subprocess.CompletedProcess[str] = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError as error:
        raise DbtInteropRuntimeError(
            "failed to execute dbt",
            help=str(error),
        ) from error
    return DbtCommandResult(
        argv=argv,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _optional_str(value: object | None) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _parse_fqn(value: object | None) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    parts: list[str] = []
    item: object
    for item in value:
        if not isinstance(item, str) or not item:
            return ()
        parts.append(item)
    return tuple(parts)
