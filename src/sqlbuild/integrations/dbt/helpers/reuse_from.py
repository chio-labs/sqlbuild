"""dbt reuse_from compile helpers."""

from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from sqlbuild.integrations.dbt.exceptions import DbtInteropConfigError, DbtInteropRuntimeError
from sqlbuild.integrations.dbt.helpers.runner import DbtRunner
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCommandResult,
    DbtReuseFromCompileResult,
)
from sqlbuild.spec.models.project import DbtReuseFromConfig


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
    dbt_relative_dir: Path = _relative_to_git_root(
        path=dbt_options.project_dir,
        git_root=git_root,
        label="dbt project directory",
    )

    with tempfile.TemporaryDirectory(prefix="sqlbuild-dbt-reuse-") as raw_temp_dir:
        temp_dir: Path = Path(raw_temp_dir)
        checkout_dir: Path = temp_dir / "checkout"
        checkout_dir.mkdir()
        _extract_git_ref(git_root=git_root, git_ref=reuse_from.git_ref, destination=checkout_dir)

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
        return DbtReuseFromCompileResult(
            git_ref=reuse_from.git_ref,
            manifest_contents=manifest_path.read_text(encoding="utf-8"),
            command=command,
        )


def _git_root(*, path: Path) -> Path:
    result: subprocess.CompletedProcess[str] = subprocess.run(
        ("git", "-C", str(path), "rev-parse", "--show-toplevel"),
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise DbtInteropConfigError(
            "dbt reuse_from requires the SQLBuild project to be in a git repository",
            help=result.stderr or result.stdout or None,
        )
    return Path(result.stdout.strip()).resolve()


def _relative_to_git_root(*, path: Path, git_root: Path, label: str) -> Path:
    resolved_path: Path = path.resolve()
    try:
        return resolved_path.relative_to(git_root)
    except ValueError as error:
        raise DbtInteropConfigError(
            f"dbt reuse_from requires the {label} to be inside the git repository",
            help=f"{resolved_path} is not under {git_root}.",
        ) from error


def _extract_git_ref(*, git_root: Path, git_ref: str, destination: Path) -> None:
    result: subprocess.CompletedProcess[bytes] = subprocess.run(
        ("git", "-C", str(git_root), "archive", git_ref),
        capture_output=True,
        check=False,
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
