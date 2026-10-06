"""Interpreter, installed code, environment, and invocation identity for compile reuse."""

from __future__ import annotations

import hashlib
import json
import os
import sys

import sqlbuild._native as native
from sqlbuild.cli.compile_reuse._helpers.project_files import file_digest
from sqlbuild.cli.compile_reuse.constants import (
    DIGEST_SIZE_BYTES,
    MISSING_ENVIRONMENT_VALUE,
    MISSING_FILE_DIGEST,
    MISSING_PATH_MTIME_NS,
    PROJECT_ROOT_PATH_MTIME_NS,
    REUSE_FORMAT_VERSION,
    TRACKED_ENVIRONMENT_PREFIXES,
    UNTRACKED_ENVIRONMENT_NAMES,
)
from sqlbuild.cli.compile_reuse.models import CompileReuseRequest, SettingsEnvironmentInputs
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


def search_path_stamps(*, project_dir: str) -> tuple[tuple[str, int], ...]:
    """Stat import search path entries, leaving the project root to the project walk."""

    project_root: str = os.path.realpath(project_dir)
    stamps: list[tuple[str, int]] = []
    for entry in sys.path:
        path: str = entry or "."
        try:
            mtime_ns: int = (
                PROJECT_ROOT_PATH_MTIME_NS
                if os.path.realpath(path) == project_root
                else os.stat(path).st_mtime_ns
            )
        except OSError:
            mtime_ns = MISSING_PATH_MTIME_NS
        stamps.append((entry, mtime_ns))
    return tuple(stamps)


def loaded_module_stamps(*, covered_paths: frozenset[str]) -> tuple[tuple[str, int, int], ...]:
    """Stat every loaded module file that the project walk does not already cover."""

    stamps: dict[str, tuple[str, int, int]] = {}
    for module in tuple(sys.modules.values()):
        path: object = getattr(module, "__file__", None)
        if not isinstance(path, str) or path in stamps or path in covered_paths:
            continue
        try:
            status: os.stat_result = os.stat(path)
        except OSError:
            continue
        stamps[path] = (path, status.st_mtime_ns, status.st_size)
    return tuple(sorted(stamps.values()))


def with_carried_module_stamps(
    *,
    current: tuple[tuple[str, int, int], ...],
    carried: tuple[tuple[str, int, int], ...],
    covered_paths: frozenset[str],
) -> tuple[tuple[str, int, int], ...]:
    """Add stored stamps of modules a reused render imported but this process did not load."""

    stamps: dict[str, tuple[str, int, int]] = {stamp[0]: stamp for stamp in carried}
    stamps.update((stamp[0], stamp) for stamp in current)
    return tuple(sorted(stamp for path, stamp in stamps.items() if path not in covered_paths))


def module_stamps_unchanged(*, stamps: tuple[tuple[str, int, int], ...]) -> bool:
    """Return whether every recorded module file still has the same stat identity."""

    for path, mtime_ns, size in stamps:
        try:
            status: os.stat_result = os.stat(path)
        except OSError:
            return False
        if status.st_mtime_ns != mtime_ns or status.st_size != size:
            return False
    return True


def tracked_environment_names(*, template_names: tuple[str, ...]) -> tuple[str, ...]:
    """Return tracked SQLBuild variables (not engine or capture settings) plus template reads."""

    prefixed: set[str] = {
        name
        for name in os.environ
        if name.startswith(TRACKED_ENVIRONMENT_PREFIXES) and name not in UNTRACKED_ENVIRONMENT_NAMES
    }
    return tuple(sorted(prefixed.union(template_names)))


def environment_digest(*, names: tuple[str, ...]) -> str:
    """Hash the current values of environment variables without retaining them."""

    digest: hashlib.blake2b = hashlib.blake2b(digest_size=DIGEST_SIZE_BYTES)
    for name in names:
        digest.update(name.encode("utf-8", "surrogateescape"))
        digest.update(b"\0")
        digest.update(
            os.environ.get(name, MISSING_ENVIRONMENT_VALUE).encode("utf-8", "surrogateescape")
        )
        digest.update(b"\0")
    return digest.hexdigest()


def settings_inputs_digest(*, inputs: tuple[SettingsEnvironmentInputs, ...]) -> str:
    """Hash the provider settings values in the environment, env files, and secrets dirs."""

    fields: list[str] = []
    for item in inputs:
        for name, value in _settings_environment(inputs=item):
            fields.extend(("env", name, value))
        for path in item.env_files:
            fields.extend(("env_file", path, _file_contents_digest(path)))
        for directory in item.secrets_dirs:
            fields.extend(("secrets_dir", directory))
            for relative_path, contents_digest in _directory_contents(directory=directory):
                fields.extend((relative_path, contents_digest))
    encoded: bytes = "\0".join(fields).encode("utf-8", "surrogateescape")
    return hashlib.blake2b(encoded, digest_size=DIGEST_SIZE_BYTES).hexdigest()


def invocation_digest(*, request: CompileReuseRequest, project_dir: str, use_color: bool) -> str:
    """Hash every command-line choice and location that can change compile output."""

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
    encoded: bytes = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=repr
    ).encode("utf-8", "surrogateescape")
    return hashlib.blake2b(encoded, digest_size=DIGEST_SIZE_BYTES).hexdigest()


def _settings_environment(*, inputs: SettingsEnvironmentInputs) -> list[tuple[str, str]]:
    names: frozenset[str] = frozenset(inputs.names)
    matched: list[tuple[str, str]] = []
    for name, value in os.environ.items():
        key: str = name if inputs.case_sensitive else name.lower()
        if key in names or key.startswith(inputs.prefixes):
            matched.append((name, value))
    return sorted(matched)


def _file_contents_digest(path: str) -> str:
    return file_digest(path=path) or MISSING_FILE_DIGEST


def _directory_contents(*, directory: str) -> list[tuple[str, str]]:
    contents: list[tuple[str, str]] = []
    for root, directories, filenames in os.walk(directory):
        directories.sort()
        for filename in sorted(filenames):
            path: str = os.path.join(root, filename)
            contents.append((os.path.relpath(path, directory), _file_contents_digest(path)))
    return contents


def entry_slot_name(*, selected_target: str | None) -> str:
    """Name the single stored entry kept for one selected target."""

    label: str = "" if selected_target is None else f"target:{selected_target}"
    return hashlib.blake2b(label.encode("utf-8"), digest_size=DIGEST_SIZE_BYTES).hexdigest()
