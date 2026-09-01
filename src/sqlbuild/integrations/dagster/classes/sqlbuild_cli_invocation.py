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
    FAILED_EXECUTION_STATUS,
    VERBOSE_FLAGS,
)

_MAX_DIAGNOSTIC_CHARS: int = 4_000


def _diagnostic_tail(value: str) -> str:
    return value[-_MAX_DIAGNOSTIC_CHARS:]


def _format_asset_failure(asset: Mapping[str, Any]) -> str:
    status: str = str(asset.get("status"))
    lines: list[str] = [f"{asset.get('kind')}:{asset.get('name')} ({status})"]
    failed_phase: object = asset.get("failed_phase")
    if failed_phase is not None:
        lines[0] += f" during {failed_phase}"
    error_message: object = asset.get("error_message")
    if error_message is not None:
        error_code: object = asset.get("error_code")
        prefix: str = f"[{error_code}] " if error_code is not None else ""
        lines.append(f"  {prefix}{error_message}")
    staging_relation: object = asset.get("staging_relation")
    if staging_relation is not None:
        lines.append(f"  staging relation: {staging_relation}")
    return "\n".join(lines)


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
                mirror_sink=sys.__stdout__,
                context=self._stdout_log_context(),
                stream_name="stdout",
            )
            stderr_future: Future[str] | None = _start_stream_future(
                executor=executor,
                source=self.process.stderr,
                sink=sys.stderr,
                mirror_sink=sys.__stderr__,
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
            "selection": " ".join(self.selection),
            "selector_file": self.selector_file_path,
        }
        description: str = (
            "SQLBuild CLI command failed with exit code "
            f"{self.returncode}: {' '.join(self.command)}"
        )
        if self.execution_payload is not None:
            incomplete_assets: list[str] = []
            failure_details: list[str] = []
            for asset in self.execution_payload.get("assets", ()):
                status: str = str(asset.get("status"))
                if status in COMPLETED_EXECUTION_STATUSES:
                    continue
                incomplete_assets.append(f"{asset.get('kind')}:{asset.get('name')} ({status})")
                failure_details.append(_format_asset_failure(asset))
            metadata["execution_status"] = str(self.execution_payload.get("status"))
            metadata["incomplete_assets"] = ", ".join(incomplete_assets)
            if failure_details:
                description += "\n\nFailures:\n\n" + "\n\n".join(failure_details)
        else:
            stdout_tail: str = _diagnostic_tail(self.stdout)
            stderr_tail: str = _diagnostic_tail(self.stderr)
            if stdout_tail:
                metadata["stdout_tail"] = stdout_tail
            if stderr_tail:
                metadata["stderr_tail"] = stderr_tail
            diagnostic: str = stderr_tail.strip() or stdout_tail.strip()
            if diagnostic:
                description += f"\n\n{diagnostic}"
        return dg.Failure(description=description, metadata=metadata)

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
        logged_failed_assets: set[tuple[str, str]] = set()
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
                    mirror_sink=sys.__stdout__,
                    context=self._stdout_log_context(),
                    stream_name="stdout",
                )
                stderr_future: Future[str] | None = _start_stream_future(
                    executor=executor,
                    source=self.process.stderr,
                    sink=sys.stderr,
                    mirror_sink=sys.__stderr__,
                    context=self.context,
                    stream_name="stderr",
                )
                try:
                    with event_path.open(mode="r", encoding="utf-8") as event_stream:
                        for result in self._yield_live_event_results(
                            dg=dg,
                            dag=dag,
                            event_stream=event_stream,
                            logged_failed_assets=logged_failed_assets,
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
        logged_failed_assets: set[tuple[str, str]],
    ) -> Iterator[Any]:
        pending: str = ""
        while True:
            chunk: str = event_stream.read()
            if chunk:
                pending += chunk
                lines: list[str] = pending.split("\n")
                pending = lines.pop()
                for line in lines:
                    yield from self._results_from_live_event_line(
                        dg=dg,
                        dag=dag,
                        line=line,
                        logged_failed_assets=logged_failed_assets,
                    )
                continue
            if self.process.poll() is not None:
                final_chunk: str = event_stream.read()
                pending += final_chunk
                for line in pending.splitlines():
                    yield from self._results_from_live_event_line(
                        dg=dg,
                        dag=dag,
                        line=line,
                        logged_failed_assets=logged_failed_assets,
                    )
                return
            time.sleep(0.01)

    def _results_from_live_event_line(
        self,
        *,
        dg: Any,
        dag: Mapping[str, Any],
        line: str,
        logged_failed_assets: set[tuple[str, str]],
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
            if isinstance(asset, Mapping):
                _ = self._log_live_asset_failure(
                    asset=asset,
                    logged_failed_assets=logged_failed_assets,
                )
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

    def _log_live_asset_failure(
        self,
        *,
        asset: Mapping[str, Any],
        logged_failed_assets: set[tuple[str, str]],
    ) -> set[tuple[str, str]]:
        if str(asset.get("status")) != FAILED_EXECUTION_STATUS:
            return logged_failed_assets
        asset_kind: str = str(asset.get("kind"))
        asset_name: str = str(asset.get("name"))
        asset_identity: tuple[str, str] = (asset_kind, asset_name)
        if asset_identity in logged_failed_assets:
            return logged_failed_assets
        logged_failed_assets.add(asset_identity)
        logger: Any = getattr(self.context, "log", None) if self.context is not None else None
        if logger is None:
            return logged_failed_assets
        asset_label: str = f"{asset_kind}:{asset_name}"
        phase: str = str(asset.get("failed_phase") or "unknown")
        code: str = str(asset.get("error_code") or "unknown")
        message: str = str(asset.get("error_message") or "Unknown SQLBuild asset failure")
        metadata: dict[str, Any] = {
            "sqlbuild_asset": asset_label,
            "sqlbuild_asset_kind": asset_kind,
            "sqlbuild_asset_name": asset_name,
            "sqlbuild_phase": phase,
            "sqlbuild_error_code": code,
            "sqlbuild_error_message": message,
            "sqlbuild_command": " ".join(self.command),
        }
        for key in ("target", "staging_relation", "duration_ms", "error_help"):
            value: object = asset.get(key)
            if value is not None:
                metadata[f"sqlbuild_{key}"] = value
        logger.error(
            "SQLBuild asset failed: asset=%s phase=%s code=%s message=%s",
            asset_label,
            phase,
            code,
            message,
            extra=metadata,
        )
        return logged_failed_assets
