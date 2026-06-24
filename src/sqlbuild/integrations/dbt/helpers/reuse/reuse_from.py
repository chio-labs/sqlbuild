"""dbt reuse_from compile helpers."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from sqlbuild.integrations.dbt.exceptions import (
    DbtInteropConfigError,
    DbtInteropRuntimeError,
    DbtReuseUnavailableError,
)
from sqlbuild.integrations.dbt.helpers.cli.runner import DbtRunner
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCommandResult,
    DbtReuseFromCompileResult,
)
from sqlbuild.integrations.dbt.types import DbtReuseUnavailableReason
from sqlbuild.spec.models.project import DbtReuseFromConfig

_REUSE_MANIFEST_CACHE_VERSION: int = 1


def compile_reuse_from_manifest(
    *,
    sqlbuild_project_dir: Path,
    dbt_options: DbtCliOptions,
    reuse_from: DbtReuseFromConfig,
    runner: DbtRunner,
) -> DbtReuseFromCompileResult:
    """Compile the dbt project from the configured reuse git ref in isolation."""

    if reuse_from.git_ref is None or reuse_from.generate_schema_name_override is None:
        raise DbtInteropConfigError("dbt reuse_from is not configured")
    if dbt_options.project_dir is None:
        raise DbtInteropConfigError("dbt project directory is not configured")

    macro_source: Path = sqlbuild_project_dir / reuse_from.generate_schema_name_override
    if not macro_source.is_file():
        raise DbtInteropConfigError(
            "dbt reuse_from generate_schema_name_override was not found",
            help=f"Expected macro override at {macro_source}.",
        )

    git_root: Path = _git_root(path=sqlbuild_project_dir)
    _raise_if_current_branch(git_root=git_root, git_ref=reuse_from.git_ref)
    dbt_relative_dir: Path = _relative_to_git_root(
        path=dbt_options.project_dir,
        git_root=git_root,
        label="dbt project directory",
    )

    with tempfile.TemporaryDirectory(prefix="sqlbuild-dbt-reuse-") as raw_temp_dir:
        temp_dir: Path = Path(raw_temp_dir)
        checkout_dir: Path = temp_dir / "checkout"
        checkout_dir.mkdir()
        archive_ref: str = _refresh_git_ref_for_archive(
            git_root=git_root,
            git_ref=reuse_from.git_ref,
            refresh=reuse_from.refresh,
            timeout_seconds=reuse_from.git_timeout_seconds,
        )
        _raise_if_missing_git_ref(
            git_root=git_root,
            git_ref=archive_ref,
            configured_ref=reuse_from.git_ref,
            project_file=sqlbuild_project_dir / "sqlbuild_project.toml",
            timeout_seconds=reuse_from.git_timeout_seconds,
        )
        commit_sha: str = _git_commit_sha(
            git_root=git_root,
            git_ref=archive_ref,
            timeout_seconds=reuse_from.git_timeout_seconds,
        )
        cache_key: str = _reuse_manifest_cache_key(
            commit_sha=commit_sha,
            dbt_relative_dir=dbt_relative_dir,
            macro_source=macro_source,
            dbt_options=dbt_options,
            dbt_executable=runner.dbt_executable,
        )
        cached_manifest_contents: str | None = _read_reuse_manifest_cache(
            sqlbuild_project_dir=sqlbuild_project_dir,
            cache_key=cache_key,
        )
        if cached_manifest_contents is not None:
            return DbtReuseFromCompileResult(
                git_ref=reuse_from.git_ref,
                manifest_contents=cached_manifest_contents,
                command=DbtCommandResult(
                    argv=("sqlbuild", "cache", "dbt-reuse-manifest"),
                    returncode=0,
                ),
                cache_hit=True,
            )
        _extract_git_ref(
            git_root=git_root,
            git_ref=archive_ref,
            destination=checkout_dir,
            timeout_seconds=reuse_from.git_timeout_seconds,
        )

        temp_dbt_project_dir: Path = checkout_dir / dbt_relative_dir
        _inject_generate_schema_name_override(
            macro_source=macro_source,
            override_relative_path=Path(reuse_from.generate_schema_name_override),
            temp_dbt_project_dir=temp_dbt_project_dir,
        )

        target_path: Path = temp_dir / "target"
        compile_options: DbtCliOptions = DbtCliOptions(
            project_dir=temp_dbt_project_dir,
            profiles_dir=dbt_options.profiles_dir,
            target=dbt_options.target,
            target_path=target_path,
            vars=dbt_options.vars,
            state=dbt_options.state,
            defer=dbt_options.defer,
        )
        if _has_dbt_dependency_file(dbt_project_dir=temp_dbt_project_dir):
            deps_command: DbtCommandResult = runner.deps(options=compile_options)
            if deps_command.returncode != 0:
                raise DbtInteropRuntimeError(
                    "dbt reuse_from deps failed",
                    help=deps_command.stderr or deps_command.stdout or None,
                )
        command: DbtCommandResult = runner.compile(options=compile_options)
        if command.returncode != 0:
            raise DbtInteropRuntimeError(
                "dbt reuse_from compile failed",
                help=command.stderr or command.stdout or None,
            )
        manifest_path: Path = target_path / "manifest.json"
        if not manifest_path.is_file():
            raise DbtInteropRuntimeError(
                "dbt reuse_from compile did not produce manifest.json",
                help=f"Expected manifest at {manifest_path}.",
            )
        manifest_contents: str = manifest_path.read_text(encoding="utf-8")
        _write_reuse_manifest_cache(
            sqlbuild_project_dir=sqlbuild_project_dir,
            cache_key=cache_key,
            manifest_contents=manifest_contents,
        )
        return DbtReuseFromCompileResult(
            git_ref=reuse_from.git_ref,
            manifest_contents=manifest_contents,
            command=command,
        )


def _git_root(*, path: Path) -> Path:
    result: subprocess.CompletedProcess[str] = _run_git_text(
        "-C", str(path), "rev-parse", "--show-toplevel"
    )
    if result.returncode != 0:
        raise DbtReuseUnavailableError(
            "dbt reuse_from requires the SQLBuild project to be in a git repository",
            reason=DbtReuseUnavailableReason.NO_GIT_REPOSITORY,
            help=result.stderr or result.stdout or None,
        )
    return Path(result.stdout.strip()).resolve()


def _has_dbt_dependency_file(*, dbt_project_dir: Path) -> bool:
    return (dbt_project_dir / "packages.yml").is_file() or (
        dbt_project_dir / "dependencies.yml"
    ).is_file()


def _git_commit_sha(*, git_root: Path, git_ref: str, timeout_seconds: int) -> str:
    result: subprocess.CompletedProcess[str] = _run_git_text(
        "-C",
        str(git_root),
        "rev-parse",
        f"{git_ref}^{{commit}}",
        timeout_seconds=timeout_seconds,
    )
    if result.returncode != 0:
        raise DbtReuseUnavailableError(
            f"dbt reuse_from git_ref '{git_ref}' could not be resolved to a commit",
            reason=DbtReuseUnavailableReason.GIT_REF_MISSING,
            help=result.stderr or result.stdout or None,
        )
    return result.stdout.strip()


def _reuse_manifest_cache_key(
    *,
    commit_sha: str,
    dbt_relative_dir: Path,
    macro_source: Path,
    dbt_options: DbtCliOptions,
    dbt_executable: str,
) -> str:
    payload: dict[str, object] = {
        "version": _REUSE_MANIFEST_CACHE_VERSION,
        "commit_sha": commit_sha,
        "dbt_executable": dbt_executable,
        "dbt_relative_dir": dbt_relative_dir.as_posix(),
        "macro_sha256": hashlib.sha256(macro_source.read_bytes()).hexdigest(),
        "profiles_dir": None if dbt_options.profiles_dir is None else str(dbt_options.profiles_dir),
        "target": dbt_options.target,
        "vars": dbt_options.vars,
        "state": None if dbt_options.state is None else str(dbt_options.state),
        "defer": dbt_options.defer,
    }
    raw_key: str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _reuse_manifest_cache_file(*, sqlbuild_project_dir: Path, cache_key: str) -> Path:
    return (
        sqlbuild_project_dir / "target" / "sqlbuild" / "cache" / "dbt_reuse" / f"{cache_key}.json"
    )


def _read_reuse_manifest_cache(*, sqlbuild_project_dir: Path, cache_key: str) -> str | None:
    cache_file: Path = _reuse_manifest_cache_file(
        sqlbuild_project_dir=sqlbuild_project_dir,
        cache_key=cache_key,
    )
    if not cache_file.is_file():
        return None
    try:
        payload: object = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != _REUSE_MANIFEST_CACHE_VERSION:
        return None
    manifest_contents: object | None = payload.get("manifest_contents")
    return manifest_contents if isinstance(manifest_contents, str) else None


def _write_reuse_manifest_cache(
    *, sqlbuild_project_dir: Path, cache_key: str, manifest_contents: str
) -> None:
    cache_file: Path = _reuse_manifest_cache_file(
        sqlbuild_project_dir=sqlbuild_project_dir,
        cache_key=cache_key,
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "version": _REUSE_MANIFEST_CACHE_VERSION,
        "manifest_contents": manifest_contents,
    }
    cache_file.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _relative_to_git_root(*, path: Path, git_root: Path, label: str) -> Path:
    resolved_path: Path = path.resolve()
    try:
        return resolved_path.relative_to(git_root)
    except ValueError as error:
        raise DbtReuseUnavailableError(
            f"dbt reuse_from requires the {label} to be inside the git repository",
            reason=DbtReuseUnavailableReason.PROJECT_OUTSIDE_GIT_ROOT,
            help=f"{resolved_path} is not under {git_root}.",
        ) from error


def _raise_if_current_branch(*, git_root: Path, git_ref: str) -> None:
    result: subprocess.CompletedProcess[str] = _run_git_text(
        "-C", str(git_root), "branch", "--show-current"
    )
    if result.returncode != 0:
        return
    current_branch: str = result.stdout.strip()
    if current_branch and current_branch == git_ref:
        raise DbtReuseUnavailableError(
            "dbt reuse_from git_ref must not be the current branch",
            reason=DbtReuseUnavailableReason.GIT_REF_IS_CURRENT_BRANCH,
            help=(
                "Choose a production-shaped branch or tag that differs from the active "
                "worktree branch."
            ),
        )


def _refresh_git_ref_for_archive(
    *, git_root: Path, git_ref: str, refresh: bool, timeout_seconds: int
) -> str:
    if not refresh:
        return git_ref
    tracking_ref: tuple[str, str, str] | None = _remote_tracking_ref(
        git_root=git_root,
        git_ref=git_ref,
    )
    if tracking_ref is None:
        return git_ref
    remote, branch, remote_ref = tracking_ref

    result: subprocess.CompletedProcess[str] = _run_git_text(
        "-C",
        str(git_root),
        "fetch",
        remote,
        branch,
        timeout_seconds=timeout_seconds,
    )
    if result.returncode != 0:
        raise DbtReuseUnavailableError(
            "dbt reuse_from git_ref could not be refreshed from its remote",
            reason=DbtReuseUnavailableReason.REMOTE_REFRESH_FAILED,
            help=result.stderr or result.stdout or None,
        )
    return remote_ref


def _raise_if_missing_git_ref(
    *,
    git_root: Path,
    git_ref: str,
    configured_ref: str,
    project_file: Path,
    timeout_seconds: int,
) -> None:
    result: subprocess.CompletedProcess[str] = _run_git_text(
        "-C",
        str(git_root),
        "rev-parse",
        "--verify",
        "--quiet",
        f"{git_ref}^{{commit}}",
        timeout_seconds=timeout_seconds,
    )
    if result.returncode == 0:
        return
    available_refs: tuple[str, ...] = _available_local_refs(git_root=git_root, limit=10)
    available_detail: str = ""
    if available_refs:
        available_detail = (
            " Available local branches/tags include: " + ", ".join(available_refs) + "."
        )
    raise DbtReuseUnavailableError(
        f"dbt reuse_from git_ref '{configured_ref}' does not exist in this repository",
        reason=DbtReuseUnavailableReason.GIT_REF_MISSING,
        help=(
            f"SQLBuild tried to archive git ref '{configured_ref}' from {git_root}. "
            "Choose the branch or tag that represents production, then update "
            f"{project_file} [dbt.reuse_from].git_ref." + available_detail
        ),
    )


def _available_local_refs(*, git_root: Path, limit: int) -> tuple[str, ...]:
    result: subprocess.CompletedProcess[str] = _run_git_text(
        "-C",
        str(git_root),
        "for-each-ref",
        "--sort=-committerdate",
        "--format=%(refname:short)",
        "refs/heads",
        "refs/tags",
    )
    if result.returncode != 0:
        return ()
    refs: list[str] = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return tuple(refs[:limit])


def _remote_tracking_ref(*, git_root: Path, git_ref: str) -> tuple[str, str, str] | None:
    remote_result: subprocess.CompletedProcess[str] = _run_git_text(
        "-C", str(git_root), "config", "--get", f"branch.{git_ref}.remote"
    )
    if remote_result.returncode != 0:
        return None
    remote: str = remote_result.stdout.strip()
    if not remote or remote == ".":
        return None

    merge_result: subprocess.CompletedProcess[str] = _run_git_text(
        "-C", str(git_root), "config", "--get", f"branch.{git_ref}.merge"
    )
    if merge_result.returncode != 0:
        return None
    merge_ref: str = merge_result.stdout.strip()
    branch: str = merge_ref.removeprefix("refs/heads/")
    if not branch or branch == merge_ref:
        return None
    return remote, branch, f"refs/remotes/{remote}/{branch}"


def _extract_git_ref(
    *, git_root: Path, git_ref: str, destination: Path, timeout_seconds: int
) -> None:
    result: subprocess.CompletedProcess[bytes] = _run_git_bytes(
        "-C", str(git_root), "archive", git_ref, timeout_seconds=timeout_seconds
    )
    if result.returncode != 0:
        stderr: str = result.stderr.decode(errors="replace")
        stdout: str = result.stdout.decode(errors="replace")
        raise DbtInteropConfigError(
            "dbt reuse_from git_ref could not be archived",
            help=stderr or stdout or None,
        )
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r|") as archive:
        archive.extractall(path=destination, filter="data")


def _run_git_text(*args: str, timeout_seconds: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ("git", *args),
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise DbtReuseUnavailableError(
            f"dbt reuse_from git command timed out after {timeout_seconds}s",
            reason=DbtReuseUnavailableReason.REMOTE_REFRESH_FAILED,
            help=(
                "Check network/SSH access or set [dbt.reuse_from].refresh = false "
                "to use the local ref."
            ),
        ) from error
    except FileNotFoundError as error:
        raise DbtInteropConfigError(
            "dbt reuse_from requires git to be installed and available on PATH",
            help=str(error),
        ) from error


def _run_git_bytes(*args: str, timeout_seconds: int = 30) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ("git", *args),
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise DbtReuseUnavailableError(
            f"dbt reuse_from git command timed out after {timeout_seconds}s",
            reason=DbtReuseUnavailableReason.REMOTE_REFRESH_FAILED,
            help=(
                "Check network/SSH access or set [dbt.reuse_from].refresh = false "
                "to use the local ref."
            ),
        ) from error
    except FileNotFoundError as error:
        raise DbtInteropConfigError(
            "dbt reuse_from requires git to be installed and available on PATH",
            help=str(error),
        ) from error


def _inject_generate_schema_name_override(
    *,
    macro_source: Path,
    override_relative_path: Path,
    temp_dbt_project_dir: Path,
) -> None:
    macro_relative_path: Path = Path(*override_relative_path.parts[2:])
    macro_destination: Path = temp_dbt_project_dir / "macros" / macro_relative_path
    macro_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(macro_source, macro_destination)
