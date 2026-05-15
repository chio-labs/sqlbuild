"""SQLBuild CLI invocation helpers for Dagster."""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import IO, Any

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
                self._cleanup_selector_file()
                raise error
        self._cleanup_selector_file()
        return self

    def _cleanup_selector_file(self) -> None:
        if self.selector_file is None:
            return
        try:
            self.selector_file.unlink(missing_ok=True)
        finally:
            self.selector_file = None

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
        """Wait for the process, log output, and yield a coarse Dagster result."""

        self.wait()
        _log_invocation(context=self.context, invocation=self)
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

    selection: tuple[str, ...]
    selector_file: Path | None
    resolved_args: tuple[str, ...]
    resolved_args, selection, selector_file = _with_selected_asset_args(
        args=tuple(args),
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
        logger.info("SQLBuild selector file:")
        logger.info("  %s", invocation.selector_file_path)
        logger.info("SQLBuild selected assets from Dagster (%s):", len(invocation.selection))
        for line in _wrap_selectors(invocation.selection):
            logger.info("  %s", line)
    for line in invocation.stdout.splitlines():
        logger.info(line)
    for line in invocation.stderr.splitlines():
        logger.warning(line)


def _wrap_selectors(selectors: tuple[str, ...], *, width: int = 100) -> tuple[str, ...]:
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
    if args[0] not in {"build", "run", "test", "audit", "seed"}:
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
        selector: object = node.get("name")
        if selector is not None:
            selectors.append(str(selector))
    if not selectors:
        return args, (), None
    selector_file: Path = _write_selector_file(tuple(selectors))
    return (*args, "--select-file", str(selector_file)), tuple(selectors), selector_file


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
