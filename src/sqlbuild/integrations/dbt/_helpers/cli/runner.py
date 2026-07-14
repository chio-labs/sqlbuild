"""dbt CLI runner and `dbt ls` parser."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence

from sqlbuild.integrations.dbt.constants import DBT_EXECUTABLE_ENV_VAR, DEFAULT_DBT_EXECUTABLE
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtLsNode,
)


def resolve_dbt_executable() -> str:
    """Return the dbt executable, honoring the DBT_EXECUTABLE override."""

    override: str | None = os.environ.get(DBT_EXECUTABLE_ENV_VAR)
    if override is not None and override.strip():
        return override.strip()
    return DEFAULT_DBT_EXECUTABLE


def build_dbt_compile_argv(
    *, dbt_executable: str, options: DbtCliOptions, full_refresh: bool = False
) -> tuple[str, ...]:
    """Build argv for dbt compile."""

    argv: tuple[str, ...] = _append_common_options(
        argv=(dbt_executable, "compile"), options=options
    )
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

    return (*_append_common_options(argv=(dbt_executable, "debug"), options=options), *args)


def build_dbt_command_argv(
    *,
    dbt_executable: str,
    command: str,
    options: DbtCliOptions,
    args: Sequence[str] = (),
) -> tuple[str, ...]:
    """Build argv for an executable dbt command with resolved common options."""

    return (*_append_common_options(argv=(dbt_executable, command), options=options), *args)


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
        argv=(dbt_executable, "ls", "--output", "json"), options=options
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


def _append_common_options(*, argv: tuple[str, ...], options: DbtCliOptions) -> tuple[str, ...]:
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
