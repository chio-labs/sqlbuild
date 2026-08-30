"""SQLBuild CLI invocation lifecycle for Dagster."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import IO, Any

from sqlbuild.integrations.dagster._helpers.imports import load_dagster
from sqlbuild.integrations.dagster._helpers.invocation import (
    _build_results_for_selected_assets,
    _build_results_from_execution_payload,
    _load_execution_payload,
    _load_execution_payload_from_path,
    _log_invocation,
    _start_stream_future,
)
from sqlbuild.integrations.dagster.constants import (
    CHECK_EVENT,
    CLONE_ASSET_EVENT,
    COMPLETED_EXECUTION_STATUSES,
    VERBOSE_FLAGS,
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
        event_jsonl_path: Path | None = None,
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
        self.event_jsonl_path: Path | None = event_jsonl_path
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
                context=self._stdout_log_context(),
                stream_name="stdout",
            )
            stderr_future: Future[str] | None = _start_stream_future(
                executor=executor,
                source=self.process.stderr,
                sink=sys.stderr,
                context=self.context,
                stream_name="stderr",
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
            pass
        else:
            try:
                self.execution_json_path.unlink(missing_ok=True)
            finally:
                self.execution_json_path = None
        if self.event_jsonl_path is not None:
            try:
                self.event_jsonl_path.unlink(missing_ok=True)
            finally:
                self.event_jsonl_path = None

    def is_successful(self) -> bool:
        """Return whether the invocation completed successfully."""

        if self.returncode is None:
            return False
        return self.returncode == 0

    def _stdout_log_context(self) -> Any:
        if VERBOSE_FLAGS.isdisjoint(self.command):
            return self.context
        return None

    def get_error(self) -> Exception | None:
        """Return a Dagster failure if the process failed."""

        if self.returncode is None or self.returncode == 0:
            return None
        dg: Any = load_dagster()
        metadata: dict[str, Any] = {
            "command": " ".join(self.command),
            "project_dir": str(self.project_dir),
            "stdout": self.stdout,
            "stderr": self.stderr,
            "selection": " ".join(self.selection),
            "selector_file": self.selector_file_path,
        }
        if self.execution_payload is not None:
            incomplete_assets: list[str] = []
            for asset in self.execution_payload.get("assets", ()):
                status: str = str(asset.get("status"))
                if status in COMPLETED_EXECUTION_STATUSES:
                    continue
                incomplete_assets.append(f"{asset.get('kind')}:{asset.get('name')} ({status})")
            metadata["execution_status"] = str(self.execution_payload.get("status"))
            metadata["incomplete_assets"] = ", ".join(incomplete_assets)
        return dg.Failure(
            description=(
                "SQLBuild CLI command failed with exit code "
                f"{self.returncode}: {' '.join(self.command)}"
            ),
            metadata=metadata,
        )

    def get_artifact(self, artifact: str) -> dict[str, Any]:
        """Read one JSON artifact from the SQLBuild project target directory."""

        path: Path = self.project_dir / "target" / artifact
        return json.loads(path.read_text(encoding="utf-8"))

    def stream(self) -> Iterator[Any]:
        """Wait for the process, log output, and yield Dagster events."""

        if self.event_jsonl_path is not None and self.dag is not None:
            yield from self._stream_with_live_events()
            return
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
        error = self.get_error()
        if error is not None and self.raise_on_error:
            raise error
        if self.dag is None:
            yield dg.MaterializeResult(metadata={"command": " ".join(self.command)})
            return
        yield from _build_results_for_selected_assets(
            dg=dg,
            dag=self.dag,
            command=self.command,
            context=self.context,
        )

    def _stream_with_live_events(self) -> Iterator[Any]:
        dg: Any = load_dagster()
        emitted_asset_keys: set[tuple[str, ...]] = set()
        emitted_check_keys: set[tuple[tuple[str, ...], str]] = set()
        event_path: Path | None = self.event_jsonl_path
        dag: Mapping[str, Any] | None = self.dag
        if event_path is None or dag is None:
            return
        original_raise_on_error: bool = self.raise_on_error
        self.raise_on_error = False
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                stdout_future: Future[str] | None = _start_stream_future(
                    executor=executor,
                    source=self.process.stdout,
                    sink=sys.stdout,
                    context=self._stdout_log_context(),
                    stream_name="stdout",
                )
                stderr_future: Future[str] | None = _start_stream_future(
                    executor=executor,
                    source=self.process.stderr,
                    sink=sys.stderr,
                    context=self.context,
                    stream_name="stderr",
                )
                try:
                    with event_path.open(mode="r", encoding="utf-8") as event_stream:
                        for result in self._yield_live_event_results(
                            dg=dg,
                            dag=dag,
                            event_stream=event_stream,
                        ):
                            if isinstance(result, dg.AssetCheckResult):
                                check_key: tuple[tuple[str, ...], str] = (
                                    tuple(result.asset_key.path),
                                    result.check_name,
                                )
                                if check_key in emitted_check_keys:
                                    continue
                                emitted_check_keys.add(check_key)
                            else:
                                asset_key: tuple[str, ...] = tuple(result.asset_key.path)
                                if asset_key in emitted_asset_keys:
                                    continue
                                emitted_asset_keys.add(asset_key)
                            yield result
                finally:
                    if self.process.poll() is None:
                        self.process.terminate()
                self.returncode = self.process.wait()
                self.stdout = stdout_future.result() if stdout_future is not None else ""
                self.stderr = stderr_future.result() if stderr_future is not None else ""
            self.execution_payload = _load_execution_payload_from_path(self.execution_json_path)
            _log_invocation(context=self.context, invocation=self)
            if self.execution_payload is not None:
                for result in _build_results_from_execution_payload(
                    dg=dg,
                    dag=dag,
                    payload=self.execution_payload,
                    command=self.command,
                    context=self.context,
                ):
                    if isinstance(result, dg.AssetCheckResult):
                        check_key = (tuple(result.asset_key.path), result.check_name)
                        if check_key in emitted_check_keys:
                            continue
                        emitted_check_keys.add(check_key)
                        yield result
                        continue
                    if isinstance(result, (dg.AssetMaterialization, dg.MaterializeResult)):
                        asset_key: tuple[str, ...] = tuple(result.asset_key.path)
                        if asset_key in emitted_asset_keys:
                            continue
                        emitted_asset_keys.add(asset_key)
                    yield result
            self.raise_on_error = original_raise_on_error
            error: Exception | None = self.get_error()
            if error is not None and self.raise_on_error:
                raise error
        finally:
            self.raise_on_error = original_raise_on_error
            self._cleanup_temp_files()

    def _yield_live_event_results(
        self,
        *,
        dg: Any,
        dag: Mapping[str, Any],
        event_stream: IO[str],
    ) -> Iterator[Any]:
        pending: str = ""
        while True:
            chunk: str = event_stream.read()
            if chunk:
                pending += chunk
                lines: list[str] = pending.split("\n")
                pending = lines.pop()
                for line in lines:
                    yield from self._results_from_live_event_line(dg=dg, dag=dag, line=line)
                continue
            if self.process.poll() is not None:
                final_chunk: str = event_stream.read()
                pending += final_chunk
                for line in pending.splitlines():
                    yield from self._results_from_live_event_line(dg=dg, dag=dag, line=line)
                return
            time.sleep(0.01)

    def _results_from_live_event_line(
        self, *, dg: Any, dag: Mapping[str, Any], line: str
    ) -> Iterator[Any]:
        if line:
            event: Any
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                return
            if not isinstance(event, Mapping) or event.get("event") not in {
                CLONE_ASSET_EVENT,
                CHECK_EVENT,
            }:
                return
            asset: object = event.get("asset")
            check: object = event.get("check")
            if not isinstance(asset, Mapping) and not isinstance(check, Mapping):
                return
            payload: Mapping[str, Any] = {
                "version": event.get("version"),
                "command": event.get("command"),
                "event": event.get("event"),
                "assets": (asset,) if isinstance(asset, Mapping) else (),
                "checks": (check,) if isinstance(check, Mapping) else (),
            }
            yield from _build_results_from_execution_payload(
                dg=dg,
                dag=dag,
                payload=payload,
                command=self.command,
                context=self.context,
            )
