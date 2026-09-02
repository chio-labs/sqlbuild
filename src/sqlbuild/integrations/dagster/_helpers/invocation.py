"""SQLBuild CLI invocation helpers for Dagster."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, TextIO

from sqlbuild.cli.output.models import IntegrationAssetResult, IntegrationResultEnvelope
from sqlbuild.integrations.dagster.constants import (
    ASSET_SELECTION_COMMANDS,
    CHECK_METADATA_EXCLUDED_KEYS,
    CHECK_NAME_SEPARATOR_CHARACTER,
    CLONE_COMMAND,
    COMPLETED_EXECUTION_STATUSES,
    DEFAULT_SELECTABLE_NODE_KINDS,
    EVENT_OUTPUT_FLAG,
    EXPLICIT_SELECTION_FLAGS,
    JSON_OUTPUT_FLAG,
    JSON_OUTPUT_FLAGS,
    LIVE_EVENT_COMMANDS,
    LOAD_COMMAND,
    LOAD_SELECTABLE_NODE_KINDS,
    LOADER_NODE_KIND,
    MATERIALIZABLE_NODE_KINDS,
    SCENARIO_CHECK_KIND,
    SCENARIO_TEST_COMMAND,
    SCENARIO_VALUE_FLAGS,
    SELECT_FILE_FLAG,
    SOURCE_NODE_KIND,
    STDERR_STREAM_NAME,
    SUCCESS_EXECUTION_STATUS,
    VIRTUAL_ENV_FLAG,
    WARNING_CHECK_SEVERITY,
)

if TYPE_CHECKING:
    from sqlbuild.integrations.dagster.classes.sqlbuild_cli_invocation import (
        SqlBuildCliInvocation,
    )


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
        for line in _wrap_selectors(selectors=invocation.selection):
            logger.info("  %s", line)


def _wrap_selectors(*, selectors: tuple[str, ...], width: int = 100) -> tuple[str, ...]:
    lines: list[str] = []
    current: str = ""
    for selector in selectors:
        candidate: str = selector if not current else f"{current} {selector}"
        if len(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = selector
    if current:
        lines.append(current)
    return tuple(lines)


def _with_selected_asset_args(
    *, args: tuple[str, ...], context: Any, dag: Mapping[str, Any] | None
) -> tuple[tuple[str, ...], tuple[str, ...], Path | None]:
    if dag is None or context is None or not args:
        return args, (), None
    scenario_test_argument_count: int = 2
    if len(args) >= scenario_test_argument_count and args[:2] == SCENARIO_TEST_COMMAND:
        return _with_selected_scenario_args(args=args, context=context, dag=dag)
    if args[0] not in ASSET_SELECTION_COMMANDS:
        return args, (), None
    if not EXPLICIT_SELECTION_FLAGS.isdisjoint(args):
        return args, (), None
    selected_keys: object = getattr(context, "selected_asset_keys", None)
    if selected_keys is None:
        return args, (), None
    selected_paths: set[tuple[str, ...]] = {tuple(key.path) for key in selected_keys}
    selectors: list[str] = []
    for node in _sort_nodes_topologically(dag=dag):
        if tuple(str(part) for part in node["asset_key"]) not in selected_paths:
            continue
        if str(node.get("kind")) not in _selectable_kinds_for_command(args[0]):
            continue
        selector: object = node.get("name")
        if selector is not None:
            selectors.append(str(selector))
    if not selectors:
        return args, (), None
    selector_file: Path = _write_selector_file(tuple(selectors))
    return (*args, SELECT_FILE_FLAG, str(selector_file)), tuple(selectors), selector_file


def _with_selected_scenario_args(
    *, args: tuple[str, ...], context: Any, dag: Mapping[str, Any]
) -> tuple[tuple[str, ...], tuple[str, ...], Path | None]:
    if _has_explicit_scenario_selector(args=args):
        return args, (), None
    selected_paths: set[tuple[str, ...]] = _selected_asset_paths(context=context)
    selected_check_keys: set[tuple[tuple[str, ...], str]] = _selected_asset_check_keys(
        context=context
    )
    if not selected_paths:
        selected_paths = {asset_key for asset_key, _check_name in selected_check_keys}
    if not selected_paths and not selected_check_keys:
        return args, (), None
    nodes_by_id: dict[str, Mapping[str, Any]] = {}
    selected_asset_ids: set[str] = set()
    for node in dag.get("nodes", ()):
        node_id: str = str(node.get("id"))
        nodes_by_id[node_id] = node
        asset_key: list[str] = []
        for part in node.get("asset_key", ()):
            asset_key.append(str(part))
        if tuple(asset_key) in selected_paths:
            selected_asset_ids.add(node_id)
    selectors: list[str] = []
    check: Mapping[str, Any]
    for check in dag.get("checks", ()):  # type: ignore[assignment]
        if str(check.get("kind")) != SCENARIO_CHECK_KIND:
            continue
        if not selected_asset_ids.intersection(
            str(id_) for id_ in check.get("checked_asset_ids", ())
        ):
            continue
        check_name: str = _dagster_check_name(check)
        if selected_check_keys and not _scenario_check_is_selected(
            check=check,
            check_name=check_name,
            nodes_by_id=nodes_by_id,
            selected_check_keys=selected_check_keys,
        ):
            continue
        selector: object = check.get("name")
        if selector is not None:
            selectors.append(str(selector))
    if not selectors:
        return args, (), None
    return (*args, *selectors), tuple(selectors), None


def _has_explicit_scenario_selector(*, args: tuple[str, ...]) -> bool:
    skip_next: bool = False
    for arg in args[2:]:
        if skip_next:
            skip_next = False
            continue
        if arg in SCENARIO_VALUE_FLAGS:
            skip_next = True
            continue
        if arg.startswith("-"):
            continue
        return True
    return False


def _scenario_check_is_selected(
    *,
    check: Mapping[str, Any],
    check_name: str,
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    selected_check_keys: set[tuple[tuple[str, ...], str]],
) -> bool:
    for asset_id in check.get("checked_asset_ids", ()):
        node: Mapping[str, Any] | None = nodes_by_id.get(str(asset_id))
        if node is None:
            continue
        asset_path: tuple[str, ...] = tuple(str(part) for part in node.get("asset_key", ()))
        if (asset_path, check_name) in selected_check_keys:
            return True
    return False


def _with_json_output_args(
    *, args: tuple[str, ...], context: Any, dag: Mapping[str, Any] | None
) -> tuple[tuple[str, ...], Path | None]:
    if dag is None or context is None or not args or _json_output_requested(args=args):
        return args, None
    if args[0] in ASSET_SELECTION_COMMANDS:
        path: Path = _create_execution_json_path()
        return (*args, JSON_OUTPUT_FLAG, str(path)), path
    scenario_test_argument_count: int = 2
    if len(args) >= scenario_test_argument_count and args[:2] == SCENARIO_TEST_COMMAND:
        path = _create_execution_json_path()
        return (*args, JSON_OUTPUT_FLAG, str(path)), path
    return args, None


def _json_output_requested(*, args: tuple[str, ...]) -> bool:
    return any(
        argument in JSON_OUTPUT_FLAGS or argument.startswith(f"{JSON_OUTPUT_FLAG}=")
        for argument in args
    )


def _caller_json_output_path(*, args: tuple[str, ...]) -> Path | None:
    for index, argument in enumerate(args):
        if argument == JSON_OUTPUT_FLAG and index + 1 < len(args):
            return Path(args[index + 1])
        prefix: str = f"{JSON_OUTPUT_FLAG}="
        if argument.startswith(prefix) and argument != prefix:
            return Path(argument.removeprefix(prefix))
    return None


def _create_execution_json_path() -> Path:
    handle: IO[str] = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="sqlbuild-dagster-execution-",
        suffix=".json",
        delete=False,
    )
    with handle:
        return Path(handle.name)


def _with_event_output_args(
    *, args: tuple[str, ...], context: Any, dag: Mapping[str, Any] | None
) -> tuple[tuple[str, ...], Path | None]:
    if (
        dag is None
        or context is None
        or not args
        or args[0] not in LIVE_EVENT_COMMANDS
        or VIRTUAL_ENV_FLAG in args
        or EVENT_OUTPUT_FLAG in args
    ):
        return args, None
    path: Path = _create_execution_event_path()
    return args, path


def _create_execution_event_path() -> Path:
    handle: IO[str] = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="sqlbuild-dagster-events-",
        suffix=".jsonl",
        delete=False,
    )
    with handle:
        return Path(handle.name)


def _start_stream_future(
    *,
    executor: ThreadPoolExecutor,
    source: IO[str] | None,
    sink: TextIO,
    mirror_sink: TextIO | None = None,
    context: Any,
    stream_name: str,
) -> Future[str] | None:
    if source is None:
        return None
    return executor.submit(
        _forward_stream,
        source=source,
        sink=sink,
        mirror_sink=mirror_sink,
        context=context,
        stream_name=stream_name,
    )


def _forward_stream(
    *,
    source: IO[str],
    sink: TextIO,
    mirror_sink: TextIO | None,
    context: Any,
    stream_name: str,
) -> str:
    captured: list[str] = []
    logger: Any | None = getattr(context, "log", None) if context is not None else None
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
            if logger is None:
                continue
            line: str = chunk.rstrip("\r\n")
            if stream_name == STDERR_STREAM_NAME:
                logger.warning("SQLBuild: %s", line)
            else:
                logger.info("SQLBuild: %s", line)
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


def _write_selector_file(selectors: tuple[str, ...]) -> Path:
    handle: IO[str] = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="sqlbuild-dagster-select-",
        suffix=".txt",
        delete=False,
    )
    with handle:
        for selector in selectors:
            handle.write(f"{selector}\n")
    return Path(handle.name)


def _build_results_for_selected_assets(
    *, dg: Any, dag: Mapping[str, Any], command: tuple[str, ...], context: Any
) -> tuple[Any, ...]:
    selected_keys: object = (
        getattr(context, "selected_asset_keys", None) if context is not None else None
    )
    selected_paths: set[tuple[str, ...]] = set()
    if selected_keys is not None:
        selected_paths = {tuple(key.path) for key in selected_keys}
    nodes: list[Mapping[str, Any]] = _sort_nodes_topologically(dag=dag)
    if selected_paths:
        selected_nodes: list[Mapping[str, Any]] = []
        for node in nodes:
            asset_path: list[str] = []
            for part in node["asset_key"]:
                asset_path.append(str(part))
            if tuple(asset_path) in selected_paths:
                selected_nodes.append(node)
        nodes = selected_nodes
    results: list[Any] = []
    for node in nodes:
        if not _is_materializable_node_kind(str(node.get("kind"))):
            continue
        asset_path = []
        for part in node["asset_key"]:
            asset_path.append(str(part))
        results.append(
            dg.MaterializeResult(
                asset_key=dg.AssetKey(asset_path),
                metadata={"command": " ".join(command), "sqlbuild_id": node.get("id")},
            )
        )
    return tuple(results)


def _selectable_kinds_for_command(command: str) -> frozenset[str]:
    if command == LOAD_COMMAND:
        return LOAD_SELECTABLE_NODE_KINDS
    return DEFAULT_SELECTABLE_NODE_KINDS


def _is_materializable_node_kind(kind: str) -> bool:
    return kind in MATERIALIZABLE_NODE_KINDS


def _load_execution_payload(stdout: str) -> Mapping[str, Any] | None:
    stripped: str = stdout.strip()
    if not stripped:
        return None
    try:
        payload: Any = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, Mapping):
        return None
    if payload.get("version") != 1:
        return None
    return payload


def _load_execution_payload_from_path(path: Path | None) -> Mapping[str, Any] | None:
    if path is None or not path.exists():
        return None
    return _load_execution_payload(path.read_text(encoding="utf-8"))


def _build_results_from_execution_payload(
    *,
    dg: Any,
    dag: Mapping[str, Any],
    payload: Mapping[str, Any],
    command: tuple[str, ...],
    context: Any,
) -> tuple[Any, ...]:
    selected_paths: set[tuple[str, ...]] = _selected_asset_paths(context=context)
    selected_check_keys: set[tuple[tuple[str, ...], str]] = _selected_asset_check_keys(
        context=context
    )
    is_clone: bool = str(payload.get("command")) == CLONE_COMMAND
    if is_clone:
        selected_paths = set()
    nodes_by_name: dict[tuple[str, str], Mapping[str, Any]] = {
        (str(node.get("kind")), str(node.get("name"))): node for node in dag.get("nodes", ())
    }
    nodes_by_id: dict[str, Mapping[str, Any]] = {
        str(node.get("id")): node for node in dag.get("nodes", ())
    }
    asset_results_by_id: dict[str, Mapping[str, Any]] = {}
    payload_asset: Mapping[str, Any]
    for payload_asset in payload.get("assets", ()):  # type: ignore[assignment]
        execution_status: str = str(payload_asset.get("status"))
        if execution_status not in COMPLETED_EXECUTION_STATUSES:
            continue
        if is_clone and execution_status != SUCCESS_EXECUTION_STATUS:
            continue
        payload_kind: str = str(payload_asset.get("kind"))
        if payload_asset.get("loader") is not None:
            payload_kind = SOURCE_NODE_KIND
        node: Mapping[str, Any] | None = nodes_by_name.get(
            (payload_kind, str(payload_asset.get("name")))
        )
        if node is None:
            continue
        asset_results_by_id[str(node.get("id"))] = payload_asset
        if str(node.get("kind")) == SOURCE_NODE_KIND and payload_asset.get("loader") is not None:
            loader_result: tuple[str, Mapping[str, Any]] | None = _loader_result_for_source_payload(
                dag=dag,
                source_node=node,
                payload_asset=payload_asset,
                loader_name=str(payload_asset["loader"]),
            )
            if loader_result is not None:
                loader_id, loader_payload = loader_result
                asset_results_by_id[loader_id] = loader_payload
    results: list[Any] = []
    for node in _sort_nodes_topologically(dag=dag):
        node_id: str = str(node.get("id"))
        execution_asset: Mapping[str, Any] | None = asset_results_by_id.get(node_id)
        if execution_asset is None:
            continue
        asset_key: Any = dg.AssetKey([str(part) for part in node["asset_key"]])
        if selected_paths and tuple(asset_key.path) not in selected_paths:
            continue
        metadata: Mapping[str, Any] = (
            _metadata_from_mapping(execution_asset)
            if execution_asset is not None
            else {"kind": "source", "name": node.get("name"), "status": "observed"}
        )
        materialization_type: Any = dg.AssetMaterialization if is_clone else dg.MaterializeResult
        results.append(
            materialization_type(
                asset_key=asset_key,
                metadata={
                    "command": " ".join(command),
                    "sqlbuild_id": node.get("id"),
                    **metadata,
                },
            )
        )
    check: Mapping[str, Any]
    seen_check_outputs: set[tuple[tuple[str, ...], str]] = set()
    for check in payload.get("checks", ()):  # type: ignore[assignment]
        check_results, seen_check_outputs = _build_check_results_from_execution_check(
            dg=dg,
            dag=dag,
            nodes_by_id=nodes_by_id,
            nodes_by_name=nodes_by_name,
            check=check,
            selected_paths=selected_paths,
            selected_check_keys=selected_check_keys,
            emitted_asset_paths=None,
            seen_check_outputs=seen_check_outputs,
        )
        results.extend(check_results)
    if _asset_check_only_context(context=context):
        return tuple(result for result in results if isinstance(result, dg.AssetCheckResult))
    return tuple(results)


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

    selected_paths: set[tuple[str, ...]] = _selected_asset_paths(context=context)
    selected_check_keys: set[tuple[tuple[str, ...], str]] = _selected_asset_check_keys(
        context=context
    )
    nodes_by_id: dict[str, Mapping[str, Any]] = {
        str(node.get("id")): node for node in dag.get("nodes", ())
    }
    nodes_by_name: dict[tuple[str, str], Mapping[str, Any]] = {
        (str(node.get("kind")), str(node.get("name"))): node for node in dag.get("nodes", ())
    }
    results: list[Any] = []
    asset: IntegrationAssetResult | None = envelope.asset
    if asset is not None and asset.status in COMPLETED_EXECUTION_STATUSES:
        node: Mapping[str, Any] | None = nodes_by_id.get(envelope.resource_id)
        loader_result: tuple[str, Mapping[str, Any]] | None = None
        same_envelope_node_ids: set[str] = set()
        if (
            node is not None
            and str(node.get("kind")) == SOURCE_NODE_KIND
            and asset.loader is not None
        ):
            loader_result = _loader_result_for_source_payload(
                dag=dag,
                source_node=node,
                payload_asset=asdict(asset),
                loader_name=asset.loader,
            )
            if loader_result is not None:
                same_envelope_node_ids.add(loader_result[0])
        if node is not None and not _live_node_dependencies_emitted(
            node=node,
            dag=dag,
            emitted_asset_paths=emitted_asset_paths,
            same_envelope_node_ids=same_envelope_node_ids,
        ):
            node = None
        asset_nodes: dict[str, tuple[Mapping[str, Any], Mapping[str, Any] | None]] = {}
        if node is not None:
            asset_nodes[str(node.get("id"))] = (node, asdict(asset))
            if loader_result is not None:
                loader_id, loader_payload = loader_result
                loader_node: Mapping[str, Any] | None = nodes_by_id.get(loader_id)
                if loader_node is not None:
                    asset_nodes[loader_id] = (loader_node, loader_payload)
        for candidate in _sort_nodes_topologically(dag=dag):
            projected: tuple[Mapping[str, Any], Mapping[str, Any] | None] | None = asset_nodes.get(
                str(candidate.get("id"))
            )
            if projected is None:
                continue
            projected_node, projected_asset = projected
            asset_key: Any = dg.AssetKey([str(part) for part in candidate["asset_key"]])
            if selected_paths and tuple(asset_key.path) not in selected_paths:
                continue
            materialization_type: Any = (
                dg.AssetMaterialization
                if envelope.command == CLONE_COMMAND
                else dg.MaterializeResult
            )
            results.append(
                materialization_type(
                    asset_key=asset_key,
                    metadata={
                        "command": " ".join(command),
                        "sqlbuild_id": candidate.get("id"),
                        "event_id": envelope.event_id,
                        "resource_attempt_id": envelope.resource_attempt_id,
                        "resource_id": envelope.resource_id,
                        "event_sequence": envelope.event_sequence,
                        "duration_ms": envelope.duration_ms,
                        **(
                            _metadata_from_mapping(projected_asset)
                            if projected_asset is not None
                            else {
                                "kind": "source",
                                "name": projected_node.get("name"),
                                "status": "observed",
                            }
                        ),
                    },
                )
            )
    seen_check_outputs: set[tuple[tuple[str, ...], str]] = set()
    for check in envelope.checks:
        check_results, seen_check_outputs = _build_check_results_from_execution_check(
            dg=dg,
            dag=dag,
            nodes_by_id=nodes_by_id,
            nodes_by_name=nodes_by_name,
            check={
                **asdict(check),
                "event_id": envelope.event_id,
                "resource_attempt_id": envelope.resource_attempt_id,
                "resource_id": envelope.resource_id,
                "event_sequence": envelope.event_sequence,
            },
            selected_paths=selected_paths,
            selected_check_keys=selected_check_keys,
            emitted_asset_paths=(
                None if _asset_check_only_context(context=context) else emitted_asset_paths
            ),
            seen_check_outputs=seen_check_outputs,
        )
        results.extend(check_results)
    if _asset_check_only_context(context=context):
        return tuple(result for result in results if isinstance(result, dg.AssetCheckResult))
    return tuple(results)


def _live_node_dependencies_emitted(
    *,
    node: Mapping[str, Any],
    dag: Mapping[str, Any],
    emitted_asset_paths: set[tuple[str, ...]],
    same_envelope_node_ids: set[str],
) -> bool:
    node_id: str = str(node.get("id"))
    nodes_by_id: dict[str, Mapping[str, Any]] = {
        str(candidate.get("id")): candidate for candidate in dag.get("nodes", ())
    }
    for edge in dag.get("edges", ()):
        if str(edge.get("to_id")) != node_id:
            continue
        upstream: Mapping[str, Any] | None = nodes_by_id.get(str(edge.get("from_id")))
        if upstream is None or not _is_materializable_node_kind(str(upstream.get("kind"))):
            continue
        upstream_id: str = str(upstream.get("id"))
        if upstream_id in same_envelope_node_ids:
            continue
        upstream_path: tuple[str, ...] = tuple(str(part) for part in upstream.get("asset_key", ()))
        if upstream_path not in emitted_asset_paths:
            return False
    return True


def _build_check_results_from_execution_check(
    *,
    dg: Any,
    dag: Mapping[str, Any],
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    nodes_by_name: Mapping[tuple[str, str], Mapping[str, Any]],
    check: Mapping[str, Any],
    selected_paths: set[tuple[str, ...]],
    selected_check_keys: set[tuple[tuple[str, ...], str]],
    emitted_asset_paths: set[tuple[str, ...]] | None,
    seen_check_outputs: set[tuple[tuple[str, ...], str]],
) -> tuple[tuple[Any, ...], set[tuple[tuple[str, ...], str]]]:
    dag_check: Mapping[str, Any] | None = _dag_check_for_execution_check(dag=dag, check=check)
    asset_ids: tuple[str, ...]
    check_name: str
    if dag_check is not None:
        asset_ids = tuple(str(asset_id) for asset_id in dag_check.get("checked_asset_ids", ()))
        check_name = _dagster_check_name(dag_check)
    else:
        asset_ids = _asset_ids_for_execution_check(check=check, nodes_by_name=nodes_by_name)
        check_name = _dagster_check_name(check)
    results: list[Any] = []
    asset_id: str
    for asset_id in asset_ids:
        node: Mapping[str, Any] | None = nodes_by_id.get(asset_id)
        if node is None:
            continue
        asset_key: Any = dg.AssetKey([str(part) for part in node["asset_key"]])
        if selected_paths and tuple(asset_key.path) not in selected_paths:
            continue
        output_key: tuple[tuple[str, ...], str] = (tuple(asset_key.path), check_name)
        if emitted_asset_paths is not None and tuple(asset_key.path) not in emitted_asset_paths:
            continue
        if selected_check_keys and output_key not in selected_check_keys:
            continue
        if output_key in seen_check_outputs:
            continue
        seen_check_outputs.add(output_key)
        results.append(
            dg.AssetCheckResult(
                passed=bool(check.get("passed")),
                asset_key=asset_key,
                check_name=check_name,
                metadata=_metadata_from_mapping(check),
                severity=_dagster_check_severity(dg=dg, check=check),
            )
        )
    return tuple(results), seen_check_outputs


def _loader_result_for_source_payload(
    *,
    dag: Mapping[str, Any],
    source_node: Mapping[str, Any],
    payload_asset: Mapping[str, Any],
    loader_name: str,
) -> tuple[str, Mapping[str, Any]] | None:
    nodes_by_id: dict[str, Mapping[str, Any]] = {
        str(node.get("id")): node for node in dag.get("nodes", ())
    }
    source_id: str = str(source_node.get("id"))
    for edge in dag.get("edges", ()):  # type: ignore[assignment]
        if str(edge.get("to_id")) != source_id:
            continue
        upstream_node: Mapping[str, Any] | None = nodes_by_id.get(str(edge.get("from_id")))
        if (
            upstream_node is None
            or str(upstream_node.get("kind")) != LOADER_NODE_KIND
            or str(upstream_node.get("name")) != loader_name
        ):
            continue
        return str(upstream_node.get("id")), {
            "kind": "loader",
            "name": upstream_node.get("name"),
            "resource_id": upstream_node.get("id"),
            "source": source_node.get("name"),
            "source_relation": payload_asset.get("target"),
            "status": payload_asset.get("status"),
        }
    return None


def _selected_asset_paths(*, context: Any) -> set[tuple[str, ...]]:
    selected_keys: object = (
        getattr(context, "selected_asset_keys", None) if context is not None else None
    )
    if selected_keys is None:
        return set()
    return {tuple(key.path) for key in selected_keys}


def _selected_asset_check_keys(*, context: Any) -> set[tuple[tuple[str, ...], str]]:
    selected_keys: object = (
        getattr(context, "selected_asset_check_keys", None) if context is not None else None
    )
    if selected_keys is None:
        return set()
    check_keys: set[tuple[tuple[str, ...], str]] = set()
    for key in selected_keys:
        asset_key: object = getattr(key, "asset_key", None)
        check_name: object = getattr(key, "name", None)
        if asset_key is None or check_name is None:
            continue
        path: object = getattr(asset_key, "path", None)
        if path is None:
            continue
        check_keys.add((tuple(str(part) for part in path), str(check_name)))
    return check_keys


def _asset_check_only_context(*, context: Any) -> bool:
    return bool(_selected_asset_check_keys(context=context)) and not bool(
        _selected_asset_paths(context=context)
    )


def _dag_check_for_execution_check(
    *, dag: Mapping[str, Any], check: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    dag_check: Mapping[str, Any]
    dag_check_id: object = check.get("dag_check_id") or check.get("check_id")
    for dag_check in dag.get("checks", ()):  # type: ignore[assignment]
        if dag_check.get("id") == dag_check_id:
            return dag_check
    return None


def _asset_ids_for_execution_check(
    *, check: Mapping[str, Any], nodes_by_name: Mapping[tuple[str, str], Mapping[str, Any]]
) -> tuple[str, ...]:
    asset_name: object = check.get("asset_name")
    if asset_name is None:
        return ()
    for kind in ("model", "source", "seed", "udf", "table_fn"):
        node: Mapping[str, Any] | None = nodes_by_name.get((kind, str(asset_name)))
        if node is not None:
            return (str(node.get("id")),)
    return ()


def _dagster_check_name(check: Mapping[str, Any]) -> str:
    parts: list[str] = [str(check.get("kind", "check")), str(check.get("name", "check"))]
    if check.get("attached_column_name") is not None:
        parts.append(str(check["attached_column_name"]))
    elif check.get("attached_target_name") is not None:
        parts.append(str(check["attached_target_name"]))
    return "__".join(_normalize_check_name(part) for part in parts if part)


def _normalize_check_name(value: str) -> str:
    normalized: str = "".join(
        char
        if char.isalnum() or char == CHECK_NAME_SEPARATOR_CHARACTER
        else CHECK_NAME_SEPARATOR_CHARACTER
        for char in value
    )
    return normalized.strip("_") or "check"


def _metadata_from_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        str(key): list(item) if isinstance(item, tuple) else item
        for key, item in value.items()
        if item is not None and key not in CHECK_METADATA_EXCLUDED_KEYS
    }


def _dagster_check_severity(*, dg: Any, check: Mapping[str, Any]) -> Any:
    if str(check.get("severity")) == WARNING_CHECK_SEVERITY:
        return dg.AssetCheckSeverity.WARN
    return dg.AssetCheckSeverity.ERROR


def _sort_nodes_topologically(*, dag: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    nodes: list[Mapping[str, Any]] = list(dag.get("nodes", ()))
    nodes_by_id: dict[str, Mapping[str, Any]] = {str(node.get("id")): node for node in nodes}
    incoming_by_id: dict[str, set[str]] = {node_id: set() for node_id in nodes_by_id}
    outgoing_by_id: dict[str, list[str]] = {node_id: [] for node_id in nodes_by_id}
    for edge in dag.get("edges", ()):
        from_id: str = str(edge.get("from_id"))
        to_id: str = str(edge.get("to_id"))
        if from_id not in nodes_by_id or to_id not in nodes_by_id:
            continue
        incoming_by_id[to_id].add(from_id)
        if to_id not in outgoing_by_id[from_id]:
            outgoing_by_id[from_id].append(to_id)

    ordered: list[Mapping[str, Any]] = []
    ready: list[str] = [node_id for node_id in nodes_by_id if not incoming_by_id[node_id]]
    while ready:
        node_id: str = ready.pop(0)
        ordered.append(nodes_by_id[node_id])
        for downstream_id in tuple(outgoing_by_id[node_id]):
            incoming_by_id[downstream_id].discard(node_id)
            if not incoming_by_id[downstream_id]:
                ready.append(downstream_id)

    if len(ordered) != len(nodes):
        return nodes
    return ordered
