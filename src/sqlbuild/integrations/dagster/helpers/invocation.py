"""SQLBuild CLI invocation helpers for Dagster."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import IO, Any, TextIO

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

    selection: tuple[str, ...]
    selector_file: Path | None
    resolved_args: tuple[str, ...]
    selected_args: tuple[str, ...]
    selected_args, selection, selector_file = _with_selected_asset_args(
        args=tuple(args),
        context=context,
        dag=dag,
    )
    execution_json_path: Path | None
    resolved_args, execution_json_path = _with_json_output_args(
        args=selected_args,
        context=context,
        dag=dag,
    )
    command: tuple[str, ...] = (*tuple(sqb_command), *resolved_args)
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
        selection=selection,
        selector_file=selector_file,
        execution_json_path=execution_json_path,
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
    if len(args) >= scenario_test_argument_count and args[0] == "scenario" and args[1] == "test":
        return _with_selected_scenario_args(args=args, context=context, dag=dag)
    if args[0] not in {"build", "run", "test", "audit", "seed", "load"}:
        return args, (), None
    if "--select" in args or "-s" in args or "--select-file" in args:
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
    return (*args, "--select-file", str(selector_file)), tuple(selectors), selector_file


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
        if str(check.get("kind")) != "scenario":
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
    value_flags: frozenset[str] = frozenset(
        {
            "--max-snapshot-rows",
            "--max-snapshot-total-rows",
            "--max-snapshot-bytes",
            "--max-snapshot-total-bytes",
        }
    )
    skip_next: bool = False
    for arg in args[2:]:
        if skip_next:
            skip_next = False
            continue
        if arg in value_flags:
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
    if dag is None or context is None or not args or "--json" in args or "--json-output" in args:
        return args, None
    if args[0] in {"build", "run", "test", "audit", "seed", "load"}:
        path: Path = _create_execution_json_path()
        return (*args, "--json-output", str(path)), path
    scenario_test_argument_count: int = 2
    if len(args) >= scenario_test_argument_count and args[0] == "scenario" and args[1] == "test":
        path = _create_execution_json_path()
        return (*args, "--json-output", str(path)), path
    return args, None


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


def _start_stream_future(
    *, executor: ThreadPoolExecutor, source: IO[str] | None, sink: TextIO
) -> Future[str] | None:
    if source is None:
        return None
    return executor.submit(_forward_stream, source=source, sink=sink)


def _forward_stream(*, source: IO[str], sink: TextIO) -> str:
    captured: list[str] = []
    try:
        for chunk in iter(source.readline, ""):
            captured.append(chunk)
            sink.write(chunk)
            sink.flush()
    finally:
        source.close()
    return "".join(captured)


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
    if command == "load":
        return frozenset({"source", "loader"})
    return frozenset({"source", "seed", "model", "udf", "table_fn"})


def _is_materializable_node_kind(kind: str) -> bool:
    return kind in {"source", "loader", "seed", "model", "udf", "table_fn"}


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
    nodes_by_name: dict[tuple[str, str], Mapping[str, Any]] = {
        (str(node.get("kind")), str(node.get("name"))): node for node in dag.get("nodes", ())
    }
    nodes_by_id: dict[str, Mapping[str, Any]] = {
        str(node.get("id")): node for node in dag.get("nodes", ())
    }
    asset_results_by_id: dict[str, Mapping[str, Any]] = {}
    payload_asset: Mapping[str, Any]
    for payload_asset in payload.get("assets", ()):  # type: ignore[assignment]
        if str(payload_asset.get("status")) not in {"success", "skipped"}:
            continue
        node: Mapping[str, Any] | None = nodes_by_name.get(
            (str(payload_asset.get("kind")), str(payload_asset.get("name")))
        )
        if node is None:
            continue
        asset_results_by_id[str(node.get("id"))] = payload_asset
        if str(node.get("kind")) == "source":
            asset_results_by_id.update(
                _loader_results_for_source_payload(
                    dag=dag,
                    source_node=node,
                    payload_asset=payload_asset,
                )
            )
    results: list[Any] = []
    for node in _sort_nodes_topologically(dag=dag):
        node_id: str = str(node.get("id"))
        execution_asset: Mapping[str, Any] | None = asset_results_by_id.get(node_id)
        if execution_asset is None and str(node.get("kind")) != "source":
            continue
        asset_key: Any = dg.AssetKey([str(part) for part in node["asset_key"]])
        if selected_paths and tuple(asset_key.path) not in selected_paths:
            continue
        metadata: Mapping[str, Any] = (
            _metadata_from_mapping(execution_asset)
            if execution_asset is not None
            else {"kind": "source", "name": node.get("name"), "status": "observed"}
        )
        results.append(
            dg.MaterializeResult(
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
            seen_check_outputs=seen_check_outputs,
        )
        results.extend(check_results)
    if _asset_check_only_context(context=context):
        return tuple(result for result in results if isinstance(result, dg.AssetCheckResult))
    return tuple(results)


def _build_check_results_from_execution_check(
    *,
    dg: Any,
    dag: Mapping[str, Any],
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    nodes_by_name: Mapping[tuple[str, str], Mapping[str, Any]],
    check: Mapping[str, Any],
    selected_paths: set[tuple[str, ...]],
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


def _loader_results_for_source_payload(
    *,
    dag: Mapping[str, Any],
    source_node: Mapping[str, Any],
    payload_asset: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    nodes_by_id: dict[str, Mapping[str, Any]] = {
        str(node.get("id")): node for node in dag.get("nodes", ())
    }
    source_id: str = str(source_node.get("id"))
    results: dict[str, Mapping[str, Any]] = {}
    for edge in dag.get("edges", ()):  # type: ignore[assignment]
        if str(edge.get("to_id")) != source_id:
            continue
        upstream_node: Mapping[str, Any] | None = nodes_by_id.get(str(edge.get("from_id")))
        if upstream_node is None or str(upstream_node.get("kind")) != "loader":
            continue
        results[str(upstream_node.get("id"))] = {
            **payload_asset,
            "kind": "loader",
            "name": upstream_node.get("name"),
            "source": source_node.get("name"),
        }
    return results


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
    check_id: object = check.get("check_id")
    dag_check: Mapping[str, Any]
    for dag_check in dag.get("checks", ()):  # type: ignore[assignment]
        if dag_check.get("id") == check_id:
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
    normalized: str = "".join(char if char.isalnum() or char == "_" else "_" for char in value)
    return normalized.strip("_") or "check"


def _metadata_from_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        str(key): item
        for key, item in value.items()
        if item is not None
        and key not in {"passed", "steps", "expected_results", "assertion_results"}
    }


def _dagster_check_severity(*, dg: Any, check: Mapping[str, Any]) -> Any:
    if str(check.get("severity")) == "warn":
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
