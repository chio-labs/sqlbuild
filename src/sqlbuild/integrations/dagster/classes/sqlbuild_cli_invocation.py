"""SQLBuild CLI invocation lifecycle for Dagster."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from sqlbuild.integrations.dagster._helpers.imports import load_dagster
from sqlbuild.integrations.dagster._helpers.invocation import (
    _build_results_for_selected_assets,
    _build_results_from_execution_payload,
    _load_execution_payload,
    _load_execution_payload_from_path,
    _log_invocation,
    _start_stream_future,
)


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
        selection: tuple[str, ...] = (),
        selector_file: Path | None = None,
        execution_json_path: Path | None = None,
    ) -> None:
        self.process: subprocess.Popen[str] = process
        self.command: tuple[str, ...] = command
        self.project_dir: Path = project_dir
        self.raise_on_error: bool = raise_on_error
        self.context: Any = context
        self.dag: Mapping[str, Any] | None = dag
        self.selection: tuple[str, ...] = selection
        self.selector_file: Path | None = selector_file
        self.selector_file_path: str = str(selector_file) if selector_file is not None else ""
        self.execution_json_path: Path | None = execution_json_path
        self.stdout: str = ""
        self.stderr: str = ""
        self.execution_payload: Mapping[str, Any] | None = None
        self.returncode: int | None = None

    def wait(self) -> SqlBuildCliInvocation:
        """Wait for the SQLBuild process to complete."""

        with ThreadPoolExecutor(max_workers=2) as executor:
            stdout_future: Future[str] | None = _start_stream_future(
                executor=executor,
                source=self.process.stdout,
                sink=sys.stdout,
            )
            stderr_future: Future[str] | None = _start_stream_future(
                executor=executor,
                source=self.process.stderr,
                sink=sys.stderr,
            )
            self.returncode = self.process.wait()
            self.stdout = stdout_future.result() if stdout_future is not None else ""
            self.stderr = stderr_future.result() if stderr_future is not None else ""
        self.execution_payload = _load_execution_payload_from_path(self.execution_json_path)
        if self.raise_on_error and not self.is_successful():
            error: Exception | None = self.get_error()
            if error is not None:
                self._cleanup_temp_files()
                raise error
        self._cleanup_temp_files()
        return self

    def _cleanup_temp_files(self) -> None:
        if self.selector_file is not None:
            try:
                self.selector_file.unlink(missing_ok=True)
            finally:
                self.selector_file = None
        if self.execution_json_path is None:
            return
        try:
            self.execution_json_path.unlink(missing_ok=True)
        finally:
            self.execution_json_path = None

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
                "selection": " ".join(self.selection),
                "selector_file": self.selector_file_path,
            },
        )

    def get_artifact(self, artifact: str) -> dict[str, Any]:
        """Read one JSON artifact from the SQLBuild project target directory."""

        path: Path = self.project_dir / "target" / artifact
        return json.loads(path.read_text(encoding="utf-8"))

    def stream(self) -> Iterator[Any]:
        """Wait for the process, log output, and yield Dagster events."""

        original_raise_on_error: bool = self.raise_on_error
        self.raise_on_error = False
        self.wait()
        self.raise_on_error = original_raise_on_error
        _log_invocation(context=self.context, invocation=self)
        dg: Any = load_dagster()
        if self.dag is not None:
            execution_payload: Mapping[str, Any] | None = self.execution_payload
            if execution_payload is None:
                execution_payload = _load_execution_payload(self.stdout)
            if execution_payload is not None:
                yield from _build_results_from_execution_payload(
                    dg=dg,
                    dag=self.dag,
                    payload=execution_payload,
                    command=self.command,
                    context=self.context,
                )
                error: Exception | None = self.get_error()
                if error is not None and self.raise_on_error:
                    raise error
                return
        if self.dag is None:
            yield dg.MaterializeResult(metadata={"command": " ".join(self.command)})
            error = self.get_error()
            if error is not None and self.raise_on_error:
                raise error
            return
        yield from _build_results_for_selected_assets(
            dg=dg,
            dag=self.dag,
            command=self.command,
            context=self.context,
        )
        error = self.get_error()
        if error is not None and self.raise_on_error:
            raise error
