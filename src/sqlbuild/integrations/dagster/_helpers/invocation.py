"""Dagster glue around native SQLBuild CLI invocation planning."""

from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, TextIO

from sqlbuild._native import (
    IntegrationResultEnvelope,
    dagster_execution_payload,
    dagster_integration_results,
    dagster_payload_results,
    dagster_selected_asset_results,
    dagster_selector_log_lines,
)

if TYPE_CHECKING:
    from sqlbuild.integrations.dagster.classes.sqlbuild_cli_invocation import (
        SqlBuildCliInvocation,
    )

_CHECK_RESULT: str = "check"
_ASSET_MATERIALIZATION: str = "materialization"


def _log_invocation(*, context: Any, invocation: SqlBuildCliInvocation) -> None:
    if context is None:
        return
    logger: Any = getattr(context, "log", None)
    if logger is None:
        return
    logger.info("SQLBuild command:")
    logger.info("  %s", " ".join(invocation.command))
    if invocation.selection:
        if invocation.selector_file_path:
            logger.info("SQLBuild selector file:")
            logger.info("  %s", invocation.selector_file_path)
        logger.info("SQLBuild selected assets from Dagster (%s):", len(invocation.selection))
        for line in dagster_selector_log_lines(selectors=list(invocation.selection)):
            logger.info("  %s", line)


def _start_stream_future(
    *,
    executor: ThreadPoolExecutor,
    source: IO[str] | None,
    sink: TextIO,
    mirror_sink: TextIO | None = None,
) -> Future[str] | None:
    if source is None:
        return None
    return executor.submit(
        _forward_stream,
        source=source,
        sink=sink,
        mirror_sink=mirror_sink,
    )


def _forward_stream(
    *,
    source: IO[str],
    sink: TextIO,
    mirror_sink: TextIO | None,
) -> str:
    captured: list[str] = []
    try:
        for chunk in iter(source.readline, ""):
            captured.append(chunk)
            sink.write(chunk)
            sink.flush()
            if mirror_sink is not None and not _streams_share_file_descriptor(
                first=sink, second=mirror_sink
            ):
                mirror_sink.write(chunk)
                mirror_sink.flush()
    finally:
        source.close()
    return "".join(captured)


def _streams_share_file_descriptor(*, first: TextIO, second: TextIO) -> bool:
    if first is second:
        return True
    try:
        return first.fileno() == second.fileno()
    except (AttributeError, OSError):
        return False


def _selected_asset_paths(*, context: Any) -> list[tuple[str, ...]]:
    selected_keys: object = (
        getattr(context, "selected_asset_keys", None) if context is not None else None
    )
    if selected_keys is None:
        return []
    paths: list[tuple[str, ...]] = []
    for key in selected_keys:
        paths.append(tuple(str(part) for part in key.path))
    return paths


def _selected_asset_check_keys(*, context: Any) -> list[tuple[tuple[str, ...], str]]:
    selected_keys: object = (
        getattr(context, "selected_asset_check_keys", None) if context is not None else None
    )
    if selected_keys is None:
        return []
    check_keys: list[tuple[tuple[str, ...], str]] = []
    for key in selected_keys:
        asset_key: object = getattr(key, "asset_key", None)
        check_name: object = getattr(key, "name", None)
        if asset_key is None or check_name is None:
            continue
        path: object = getattr(asset_key, "path", None)
        if path is None:
            continue
        check_keys.append((tuple(str(part) for part in path), str(check_name)))
    return check_keys


def _check_selection_is_explicit(*, context: Any) -> bool:
    return context is not None and getattr(context, "selected_asset_check_keys", None) is not None


def _dagster_events(*, dg: Any, plans: list[tuple[Any, ...]]) -> tuple[Any, ...]:
    events: list[Any] = []
    for kind, path, metadata, check_name, passed, warn in plans:
        asset_key: Any = dg.AssetKey(path)
        if kind == _CHECK_RESULT:
            events.append(
                dg.AssetCheckResult(
                    passed=passed,
                    asset_key=asset_key,
                    check_name=check_name,
                    metadata=metadata,
                    severity=dg.AssetCheckSeverity.WARN if warn else dg.AssetCheckSeverity.ERROR,
                )
            )
            continue
        event_type: Any = (
            dg.AssetMaterialization if kind == _ASSET_MATERIALIZATION else dg.MaterializeResult
        )
        events.append(event_type(asset_key=asset_key, metadata=metadata))
    return tuple(events)


def _build_results_for_selected_assets(
    *, dg: Any, dag: Mapping[str, Any], command: tuple[str, ...], context: Any
) -> tuple[Any, ...]:
    return _dagster_events(
        dg=dg,
        plans=dagster_selected_asset_results(
            dag=dag,
            command=list(command),
            selected_asset_paths=_selected_asset_paths(context=context),
        ),
    )


def _load_execution_payload(stdout: str) -> Mapping[str, Any] | None:
    return dagster_execution_payload(text=stdout)


def _load_execution_payload_from_path(path: Path | None) -> Mapping[str, Any] | None:
    if path is None or not path.exists():
        return None
    return dagster_execution_payload(text=path.read_text(encoding="utf-8"))


def _build_results_from_execution_payload(
    *,
    dg: Any,
    dag: Mapping[str, Any],
    payload: Mapping[str, Any],
    command: tuple[str, ...],
    context: Any,
) -> tuple[Any, ...]:
    return _dagster_events(
        dg=dg,
        plans=dagster_payload_results(
            dag=dag,
            payload=payload,
            command=list(command),
            selected_asset_paths=_selected_asset_paths(context=context),
            selected_check_keys=_selected_asset_check_keys(context=context),
            check_selection_is_explicit=_check_selection_is_explicit(context=context),
        ),
    )


def _build_results_from_integration_result(
    *,
    dg: Any,
    dag: Mapping[str, Any],
    envelope: IntegrationResultEnvelope,
    command: tuple[str, ...],
    context: Any,
    emitted_asset_paths: set[tuple[str, ...]],
) -> tuple[Any, ...]:
    """Translate one canonical integration result directly into Dagster events."""

    return _dagster_events(
        dg=dg,
        plans=dagster_integration_results(
            dag=dag,
            envelope=envelope,
            command=list(command),
            selected_asset_paths=_selected_asset_paths(context=context),
            selected_check_keys=_selected_asset_check_keys(context=context),
            check_selection_is_explicit=_check_selection_is_explicit(context=context),
            emitted_asset_paths=list(emitted_asset_paths),
        ),
    )
