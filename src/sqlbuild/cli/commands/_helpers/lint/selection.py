"""Canonical model selector resolution for lint and format CLI commands."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.classes.selected_contract_input_discoverer import (
    SelectedContractInputDiscoverer,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveredSqlModelFile
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.selection.selection import resolve_project_selectors
from sqlbuild.lint.constants import LINT_DIRECTORY_NAMES, PARENT_PATH_SEGMENT, SQL_FILE_SUFFIX
from sqlbuild.lint.main.scan_fixture_typed_null_candidates import (
    scan_fixture_typed_null_candidates,
)
from sqlbuild.lint.models import FixtureNullCandidateScan
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)

_PATH_SEPARATOR: str = "/"
_GRAPH_SELECTOR_MARKERS: tuple[str, ...] = ("+", ":", "~", "/", "\\", ",")


def resolve_lint_inputs(
    *, project_dir: Path, select: tuple[str, ...], exclude: tuple[str, ...]
) -> tuple[BaseAdapter, frozenset[Path] | None, DiscoveredProjectInputs]:
    """Resolve the adapter and optional model-file scope through canonical selectors."""

    lint_paths: frozenset[Path] | None = _resolve_lint_paths(
        project_dir=project_dir,
        select=select,
        exclude=exclude,
    )
    if lint_paths is not None:
        _validate_selected_paths(paths=lint_paths)
        candidates: FixtureNullCandidateScan = scan_fixture_typed_null_candidates(
            project_dir=project_dir,
            selected_paths=lint_paths,
        )
        discovered: DiscoveredProjectInputs = SelectedContractInputDiscoverer.discover(
            project_dir=project_dir,
            selected_test_paths=candidates.paths,
            referenced_model_names=candidates.model_names,
        )
        adapter: BaseAdapter = _resolve_discovered_adapter(
            project_dir=project_dir,
            discovered=discovered,
        )
        return adapter, lint_paths, discovered
    discovered = discover_project_inputs(
        project_dir=project_dir,
        sql_analysis_enabled_override=False,
        extract_output_column_locations=False,
    )
    adapter = _resolve_discovered_adapter(
        project_dir=project_dir,
        discovered=discovered,
    )
    if not select and not exclude:
        return adapter, None, discovered
    combined_paths: frozenset[Path] | None = _resolve_combined_lint_paths(
        project_dir=project_dir,
        discovered=discovered,
        adapter=adapter,
        select=select,
        exclude=exclude,
    )
    if combined_paths is not None:
        _validate_selected_paths(paths=combined_paths)
        return adapter, combined_paths, discovered
    paths: frozenset[Path] = _resolve_model_paths(
        project_dir=project_dir,
        discovered=discovered,
        adapter=adapter,
        select=select,
        exclude=exclude,
    )
    _validate_selected_paths(paths=paths)
    return adapter, paths, discovered


def _resolve_model_paths(
    *,
    project_dir: Path,
    discovered: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
) -> frozenset[Path]:
    """Resolve model selectors to authored model paths."""

    exact_paths: frozenset[Path] | None = _resolve_exact_model_paths(
        project_dir=project_dir,
        discovered=discovered,
        select=select,
        exclude=exclude,
    )
    if exact_paths is not None:
        return exact_paths
    graph: ProjectGraph = build_project_graph(discovered_inputs=discovered, adapter=adapter)
    selected_keys: frozenset[CompiledObjectKey] = resolve_project_selectors(
        select=select,
        exclude=exclude,
        all_keys=graph.all_keys,
        upstream_deps=graph.upstream_deps,
        downstream_deps=graph.downstream_deps,
        tag_index=graph.tag_index,
        path_index=graph.path_index,
    )
    selected_names: frozenset[str] = frozenset(
        key.name for key in selected_keys if key.resource_type == CompiledResourceType.MODEL
    )
    return frozenset(
        (project_dir / model.relative_path).resolve()
        for model in graph.project.models
        if model.name in selected_names
    )


def _resolve_combined_lint_paths(
    *,
    project_dir: Path,
    discovered: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
) -> frozenset[Path] | None:
    """Resolve default or path-based format scopes before graph selector expansion."""

    if any(not selector.strip() for selector in (*select, *exclude)):
        return None
    selected_path_tokens, selected_model_tokens = _partition_lint_selectors(select)
    excluded_path_tokens, excluded_model_tokens = _partition_lint_selectors(exclude)
    has_path_selector: bool = bool(selected_path_tokens or excluded_path_tokens)
    if not has_path_selector and select:
        return None
    all_paths: frozenset[Path] = frozenset(
        _paths_for_prefixes(project_dir=project_dir, prefixes=())
    )
    if select:
        selected: set[Path] = set(
            _paths_for_prefixes(project_dir=project_dir, prefixes=selected_path_tokens)
            if selected_path_tokens
            else ()
        )
        if selected_model_tokens:
            selected.update(
                _resolve_model_paths(
                    project_dir=project_dir,
                    discovered=discovered,
                    adapter=adapter,
                    select=selected_model_tokens,
                    exclude=(),
                )
            )
    else:
        selected = set(all_paths)
    excluded: set[Path] = set(
        _paths_for_prefixes(project_dir=project_dir, prefixes=excluded_path_tokens)
        if excluded_path_tokens
        else ()
    )
    if excluded_model_tokens:
        excluded.update(
            _resolve_model_paths(
                project_dir=project_dir,
                discovered=discovered,
                adapter=adapter,
                select=excluded_model_tokens,
                exclude=(),
            )
        )
    return frozenset(selected - excluded)


def _partition_lint_selectors(
    raw_selectors: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Separate valid formatter-root paths from model selectors."""

    path_tokens: list[str] = []
    model_tokens: list[str] = []
    for raw_selector in raw_selectors:
        for token in raw_selector.split():
            _reject_unknown_lint_root(token)
            prefixes: tuple[str, ...] | None = _lint_path_prefixes(raw_selectors=(token,))
            if prefixes is not None:
                path_tokens.extend(prefixes)
            else:
                model_tokens.append(token)
    return tuple(path_tokens), tuple(model_tokens)


def _resolve_discovered_adapter(
    *, project_dir: Path, discovered: DiscoveredProjectInputs
) -> BaseAdapter:
    return resolve_adapter(
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered.project_config,
            local_config=discovered.local_config,
        ),
        project_dir=project_dir,
    )


def _resolve_lint_paths(
    *,
    project_dir: Path,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
) -> frozenset[Path] | None:
    """Resolve simple path selectors across every formatter-owned SQL root."""

    selected_prefixes: tuple[str, ...] | None = _lint_path_prefixes(raw_selectors=select)
    excluded_prefixes: tuple[str, ...] | None = _lint_path_prefixes(raw_selectors=exclude)
    if selected_prefixes is None or excluded_prefixes is None:
        return None
    selected: tuple[Path, ...] = _paths_for_prefixes(
        project_dir=project_dir,
        prefixes=selected_prefixes,
    )
    return frozenset(
        path
        for path in selected
        if not _matches_path_prefix(
            relative_path=path.relative_to(project_dir.resolve()).as_posix(),
            prefixes=excluded_prefixes,
        )
    )


def _paths_for_prefixes(*, project_dir: Path, prefixes: tuple[str, ...]) -> tuple[Path, ...]:
    roots: tuple[Path, ...] = (
        tuple(project_dir / prefix for prefix in prefixes)
        if prefixes
        else tuple(project_dir / directory_name for directory_name in LINT_DIRECTORY_NAMES)
    )
    paths: set[Path] = set()
    for root in roots:
        if root.is_file() and root.suffix.casefold() == SQL_FILE_SUFFIX:
            paths.add(root.resolve())
        elif root.is_dir():
            paths.update(file_path.resolve() for file_path in root.rglob("*.sql"))
    return tuple(sorted(paths))


def _lint_path_prefixes(*, raw_selectors: tuple[str, ...]) -> tuple[str, ...] | None:
    prefixes: list[str] = []
    for raw_selector in raw_selectors:
        if not raw_selector.strip():
            return None
        for token in raw_selector.split():
            normalized: str = token.replace("\\", "/")
            if not normalized.startswith("path:") and not _is_bare_lint_path(normalized):
                return None
            prefix: str = normalized.removeprefix("path:").strip("/")
            if any(marker in prefix for marker in ("+", "~", ",")):
                return None
            parts: tuple[str, ...] = tuple(part for part in prefix.split("/") if part)
            if not parts or parts[0] not in LINT_DIRECTORY_NAMES or PARENT_PATH_SEGMENT in parts:
                return None
            prefixes.append("/".join(parts))
    return tuple(prefixes)


def _is_bare_lint_path(token: str) -> bool:
    """Treat `models/orders.sql`-style tokens as formatter paths without a `path:` prefix."""

    first_segment: str = token.split(_PATH_SEPARATOR, 1)[0]
    return _PATH_SEPARATOR in token and first_segment in LINT_DIRECTORY_NAMES


def _reject_unknown_lint_root(token: str) -> None:
    normalized: str = token.replace("\\", "/")
    if not normalized.startswith("path:"):
        return
    root: str = normalized.removeprefix("path:").strip(_PATH_SEPARATOR).split(_PATH_SEPARATOR, 1)[0]
    if root in LINT_DIRECTORY_NAMES:
        return
    raise PlannerInputError(
        "format path selectors must start with one of: "
        + ", ".join(f"'{name}/'" for name in LINT_DIRECTORY_NAMES),
        code="S012",
    )


def _matches_path_prefix(*, relative_path: str, prefixes: tuple[str, ...]) -> bool:
    return any(
        relative_path == prefix or relative_path.startswith(f"{prefix}/") for prefix in prefixes
    )


def _resolve_exact_model_paths(
    *,
    project_dir: Path,
    discovered: DiscoveredProjectInputs,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
) -> frozenset[Path] | None:
    """Resolve unexpanded model-name selectors without compiling the project graph."""

    model_names_and_paths: list[tuple[str, Path]] = []
    model_file: DiscoveredSqlModelFile
    for model_file in discovered.model_files:
        configured_name: object = model_file.header_values.get("name")
        model_name: str = (
            configured_name
            if isinstance(configured_name, str) and configured_name
            else model_file.relative_path.stem
        )
        model_names_and_paths.append(
            (model_name, (project_dir / model_file.relative_path).resolve())
        )
    selected_names: frozenset[str] | None = _exact_names(raw_selectors=select)
    excluded_names: frozenset[str] | None = _exact_names(raw_selectors=exclude)
    if selected_names is None or excluded_names is None:
        return None
    available_names: frozenset[str] = frozenset(name for name, _path in model_names_and_paths)
    unknown_names: frozenset[str] = (selected_names | excluded_names) - available_names
    if unknown_names:
        unknown_name: str = sorted(unknown_names)[0]
        raise PlannerInputError(f"unknown selector name '{unknown_name}'", code="S007")
    names: frozenset[str] = selected_names or available_names
    return frozenset(
        path for name, path in model_names_and_paths if name in names and name not in excluded_names
    )


def _exact_names(*, raw_selectors: tuple[str, ...]) -> frozenset[str] | None:
    """Return plain model names, or None when canonical graph resolution is required."""

    names: set[str] = set()
    raw_selector: str
    for raw_selector in raw_selectors:
        if not raw_selector.strip():
            return None
        token: str
        for token in raw_selector.split():
            if any(marker in token for marker in _GRAPH_SELECTOR_MARKERS):
                return None
            names.add(token)
    return frozenset(names)


def _validate_selected_paths(*, paths: frozenset[Path]) -> None:
    """Reject lint selections that contain no SQL files."""

    if not paths:
        raise PlannerInputError(
            "lint selection matched no SQL files",
            code="S007",
        )
