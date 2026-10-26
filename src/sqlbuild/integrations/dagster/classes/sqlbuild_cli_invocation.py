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

from sqlbuild._native import (
    IntegrationAssetResult,
    IntegrationResultEnvelope,
    dagster_failure,
    dagster_live_failure,
)
from sqlbuild.integrations.dagster._helpers.imports import load_dagster
from sqlbuild.integrations.dagster._helpers.invocation import (
    _build_results_for_selected_assets,
    _build_results_from_execution_payload,
    _build_results_from_integration_result,
    _load_execution_payload,
    _load_execution_payload_from_path,
    _log_failed_check,
    _log_invocation,
    _start_stream_future,
)
from sqlbuild.integrations.dagster.constants import FAILED_EXECUTION_STATUS
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError


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
        self.execution_json_owned: bool = True
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
            )
            stderr_future: Future[str] | None = _start_stream_future(
                executor=executor,
                source=self.process.stderr,
                sink=sys.stderr,
                mirror_sink=sys.__stderr__,
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
        if self.execution_json_path is None or not self.execution_json_owned:
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

    def get_error(self) -> Exception | None:
        """Return a Dagster failure if the process failed."""

        if self.returncode is None or self.returncode == 0:
            return None
        dg: Any = load_dagster()
        description: str
        metadata: dict[str, Any]
        description, metadata = dagster_failure(
            command=list(self.command),
            project_dir=self.project_dir,
            selection=list(self.selection),
            selector_file=self.selector_file_path,
            returncode=self.returncode,
            execution_payload=self.execution_payload,
            stdout=self.stdout,
            stderr=self.stderr,
        )
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
                self.execution_payload = execution_payload
                for result in _build_results_from_execution_payload(
                    dg=dg,
                    dag=self.dag,
                    payload=execution_payload,
                    command=self.command,
                    context=self.context,
                ):
                    if isinstance(result, dg.AssetCheckResult):
                        _log_failed_check(context=self.context, dg=dg, result=result)
                    yield result
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
                )
                stderr_future: Future[str] | None = _start_stream_future(
                    executor=executor,
                    source=self.process.stderr,
                    sink=sys.stderr,
                    mirror_sink=sys.__stderr__,
                )
                try:
                    with event_path.open(mode="r", encoding="utf-8") as event_stream:
                        for result in self._yield_live_event_results(
                            dg=dg,
                            dag=dag,
                            event_stream=event_stream,
                            logged_failed_assets=logged_failed_assets,
                            emitted_asset_keys=emitted_asset_keys,
                        ):
                            if isinstance(result, dg.AssetCheckResult):
                                check_key: tuple[tuple[str, ...], str] = (
                                    tuple(result.asset_key.path),
                                    result.check_name,
                                )
                                if check_key in emitted_check_keys:
                                    continue
                                emitted_check_keys.add(check_key)
                                _log_failed_check(context=self.context, dg=dg, result=result)
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
            if self.execution_payload is None:
                self.execution_payload = _load_execution_payload(self.stdout)
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
                        _log_failed_check(context=self.context, dg=dg, result=result)
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
        emitted_asset_keys: set[tuple[str, ...]],
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
                        emitted_asset_keys=emitted_asset_keys,
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
                        emitted_asset_keys=emitted_asset_keys,
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
        emitted_asset_keys: set[tuple[str, ...]],
    ) -> Iterator[Any]:
        if line:
            try:
                envelope: IntegrationResultEnvelope = IntegrationResultEnvelope.from_json(line)
            except ObservabilityValidationError:
                try:
                    envelope = IntegrationResultEnvelope.from_json_without_optional_enrichment(line)
                except ObservabilityValidationError:
                    self._warn_invalid_integration_record()
                    return
            if envelope.asset is not None:
                _ = self._log_live_asset_failure(
                    asset=envelope.asset,
                    envelope=envelope,
                    logged_failed_assets=logged_failed_assets,
                )
            yield from _build_results_from_integration_result(
                dg=dg,
                dag=dag,
                envelope=envelope,
                command=self.command,
                context=self.context,
                emitted_asset_paths=emitted_asset_keys,
            )

    def _warn_invalid_integration_record(self) -> None:
        message: str = "Ignored invalid SQLBuild integration result record"
        logger: Any = getattr(self.context, "log", None) if self.context is not None else None
        if logger is not None:
            logger.warning(message)
            return
        sys.stderr.write(f"{message}\n")
        sys.stderr.flush()

    def _log_live_asset_failure(
        self,
        *,
        asset: IntegrationAssetResult,
        envelope: IntegrationResultEnvelope,
        logged_failed_assets: set[tuple[str, str]],
    ) -> set[tuple[str, str]]:
        if asset.status != FAILED_EXECUTION_STATUS:
            return logged_failed_assets
        asset_kind: str = asset.kind
        asset_name: str = asset.name
        asset_identity: tuple[str, str] = (asset_kind, asset_name)
        if asset_identity in logged_failed_assets:
            return logged_failed_assets
        logged_failed_assets.add(asset_identity)
        logger: Any = getattr(self.context, "log", None) if self.context is not None else None
        if logger is None:
            return logged_failed_assets
        log_arguments: list[str]
        metadata: dict[str, Any]
        log_arguments, metadata = dagster_live_failure(
            asset=asset, envelope=envelope, command=list(self.command)
        )
        logger.error(
            "SQLBuild asset failed: asset=%s phase=%s code=%s message=%s",
            *log_arguments,
            extra=metadata,
        )
        return logged_failed_assets
