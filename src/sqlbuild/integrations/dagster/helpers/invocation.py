"""SQLBuild CLI invocation helpers for Dagster."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from sqlbuild.integrations.dagster.helpers.imports import load_dagster


class SqlBuildCliInvocation:
    """A running or completed SQLBuild CLI subprocess."""

    def __init__(
        self,
        *,
        process: subprocess.Popen[str],
        command: tuple[str, ...],
        project_dir: Path,
        raise_on_error: bool = True,
        context: Any = None,
        dag: Mapping[str, Any] | None = None,
    ) -> None:
        self.process: subprocess.Popen[str] = process
        self.command: tuple[str, ...] = command
        self.project_dir: Path = project_dir
        self.raise_on_error: bool = raise_on_error
        self.context: Any = context
        self.dag: Mapping[str, Any] | None = dag
        self.stdout: str = ""
        self.stderr: str = ""
        self.returncode: int | None = None

    def wait(self) -> SqlBuildCliInvocation:
        """Wait for the SQLBuild process to complete."""

        stdout: str
        stderr: str
        stdout, stderr = self.process.communicate()
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = self.process.returncode
        if self.raise_on_error and not self.is_successful():
            error: Exception | None = self.get_error()
            if error is not None:
                raise error
        return self

    def is_successful(self) -> bool:
        """Return whether the invocation completed successfully."""

        if self.returncode is None:
            return False
        return self.returncode == 0

    def get_error(self) -> Exception | None:
        """Return a Dagster failure if the process failed."""

        if self.returncode is None or self.returncode == 0:
            return None
        dg: Any = load_dagster()
        return dg.Failure(
            description=(
                "SQLBuild CLI command failed with exit code "
                f"{self.returncode}: {' '.join(self.command)}"
            ),
            metadata={
                "command": " ".join(self.command),
                "project_dir": str(self.project_dir),
                "stdout": self.stdout,
                "stderr": self.stderr,
            },
        )

    def get_artifact(self, artifact: str) -> dict[str, Any]:
        """Read one JSON artifact from the SQLBuild project target directory."""

        path: Path = self.project_dir / "target" / artifact
        return json.loads(path.read_text(encoding="utf-8"))

    def stream(self) -> Iterator[Any]:
        """Wait for the process, log output, and yield a coarse Dagster result."""

        self.wait()
        _log_cli_output(context=self.context, stdout=self.stdout, stderr=self.stderr)
        dg: Any = load_dagster()
        if self.dag is None:
            yield dg.MaterializeResult(metadata={"command": " ".join(self.command)})
            return
        yield from _build_results_for_selected_assets(
            dg=dg,
            dag=self.dag,
            command=self.command,
            context=self.context,
        )


def start_sqlbuild_cli_invocation(
    *,
    sqb_command: Sequence[str],
    args: Sequence[str],
    project_dir: Path,
    raise_on_error: bool,
    context: Any = None,
    dag: Mapping[str, Any] | None = None,
) -> SqlBuildCliInvocation:
    """Start a SQLBuild CLI subprocess and return its invocation wrapper."""

    command: tuple[str, ...] = (*tuple(sqb_command), *tuple(args))
    process: subprocess.Popen[str] = subprocess.Popen(
        command,
        cwd=project_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return SqlBuildCliInvocation(
        process=process,
        command=command,
        project_dir=project_dir,
        raise_on_error=raise_on_error,
        context=context,
        dag=dag,
    )


def _log_cli_output(*, context: Any, stdout: str, stderr: str) -> None:
    if context is None:
        return
    logger: Any = getattr(context, "log", None)
    if logger is None:
        return
    for line in stdout.splitlines():
        logger.info(line)
    for line in stderr.splitlines():
        logger.warning(line)


def _build_results_for_selected_assets(
    *, dg: Any, dag: Mapping[str, Any], command: tuple[str, ...], context: Any
) -> tuple[Any, ...]:
    selected_keys: object = (
        getattr(context, "selected_asset_keys", None) if context is not None else None
    )
    selected_paths: set[tuple[str, ...]] = set()
    if selected_keys is not None:
        selected_paths = {tuple(key.path) for key in selected_keys}
    nodes: list[Mapping[str, Any]] = list(dag.get("nodes", ()))
    if selected_paths:
        nodes = [
            node
            for node in nodes
            if tuple(str(part) for part in node["asset_key"]) in selected_paths
        ]
    return tuple(
        dg.MaterializeResult(
            asset_key=dg.AssetKey([str(part) for part in node["asset_key"]]),
            metadata={"command": " ".join(command), "sqlbuild_id": node.get("id")},
        )
        for node in nodes
        if str(node.get("kind")) in {"source", "seed", "model", "function"}
    )
