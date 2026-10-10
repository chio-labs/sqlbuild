"""Interpreter and invocation facts the Python host supplies to native compile reuse."""

from __future__ import annotations

import json
import os
import stat
import sys

import sqlbuild._native as native
from sqlbuild.cli.compile_reuse.constants import OUTPUT_FILE_DESCRIPTORS, REUSE_FORMAT_VERSION
from sqlbuild.cli.compile_reuse.models import CompileReuseRequest
from sqlbuild.compiler.frontier.main.resolve_compiler_engine import resolve_compiler_engine


def runtime_identity() -> dict[str, str]:
    """Return the interpreter and native build identity that produced a compile."""

    return {
        "format": str(REUSE_FORMAT_VERSION),
        "python": sys.version,
        "executable": sys.executable,
        "platform": sys.platform,
        "cache_tag": str(sys.implementation.cache_tag),
        "native_build": str(native.BUILD_IDENTITY),
    }


def invocation_identity(
    *, request: CompileReuseRequest, project_dir: str, use_color: bool
) -> bytes:
    """Encode every command-line choice and location that can change compile output."""

    payload: dict[str, object] = {
        "project_dir": project_dir,
        "requested_project_dir": None if request.project_dir is None else str(request.project_dir),
        "cwd": os.getcwd(),
        "no_sql_validation": request.no_sql_validation,
        "defer_to": request.defer_to,
        "selected_target": request.selected_target,
        "json_output": request.json_output,
        "manifest": request.manifest,
        "dag_path": request.dag_path,
        "no_color": request.no_color,
        "use_color": use_color,
        "lineage_mode": request.lineage_mode,
        "select": list(request.select),
        "exclude": list(request.exclude),
        "cli_vars": request.cli_vars,
        "sys_path": list(sys.path),
        "compiler_engine": resolve_compiler_engine().value,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=repr).encode(
        "utf-8", "surrogateescape"
    )


def redirected_output_files() -> list[tuple[int, int]]:
    """Identify stdout and stderr files, which hold this command's output, not its inputs."""

    identities: set[tuple[int, int]] = set()
    for descriptor in OUTPUT_FILE_DESCRIPTORS:
        try:
            status: os.stat_result = os.fstat(descriptor)
        except OSError:
            continue
        if stat.S_ISREG(status.st_mode):
            identities.add((status.st_dev, status.st_ino))
    return sorted(identities)
