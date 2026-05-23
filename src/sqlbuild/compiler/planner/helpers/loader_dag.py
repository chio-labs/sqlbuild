"""Loader DAG planning helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.spec.models.source import SourceEntry


def expand_selected_loader_dependencies(
    *,
    project: CompiledProject,
    selected_keys: frozenset[CompiledObjectKey],
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> tuple[frozenset[CompiledObjectKey], dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]]:
    """Add intermediate loader nodes needed by selected managed source loads."""

    loader_by_name: dict[str, DiscoveredLoaderFunction] = {
        loader.name: loader for loader in project.loader_functions
    }
    loader_name_by_function: dict[object, str] = {
        loader.function: loader.name for loader in project.loader_functions
    }
    source_by_loader: dict[str, SourceEntry] = {
        source.source_entry.loader: source.source_entry
        for source in project.sources
        if source.source_entry.loader is not None
    }
    expanded_upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = dict(upstream_deps)
    expanded_selected: set[CompiledObjectKey] = set(selected_keys)

    source_by_name: dict[str, SourceEntry] = {
        source.source_entry.name: source.source_entry for source in project.sources
    }
    selected_key: CompiledObjectKey
    for selected_key in selected_keys:
        if selected_key.resource_type != CompiledResourceType.SOURCE:
            continue
        source_entry: SourceEntry | None = source_by_name.get(selected_key.name)
        if source_entry is None or source_entry.loader is None:
            continue
        loader_function: DiscoveredLoaderFunction | None = loader_by_name.get(source_entry.loader)
        if loader_function is None:
            continue
        expanded_upstream[selected_key] = _dependency_keys(
            loader_function=loader_function,
            loader_name_by_function=loader_name_by_function,
            source_by_loader=source_by_loader,
        )
        expanded_selected.update(
            _select_dependency_closure(
                loader_function=loader_function,
                loader_by_name=loader_by_name,
                loader_name_by_function=loader_name_by_function,
                source_by_loader=source_by_loader,
                upstream_deps=expanded_upstream,
            )
        )

    return frozenset(expanded_selected), expanded_upstream


def build_intermediate_source_map(
    *, project: CompiledProject, selected_keys: frozenset[CompiledObjectKey]
) -> dict[str, SourceEntry]:
    """Return synthetic source entries for selected intermediate loader nodes."""

    source_by_loader: dict[str, SourceEntry] = {
        source.source_entry.loader: source.source_entry
        for source in project.sources
        if source.source_entry.loader is not None
    }
    loader_by_name: dict[str, DiscoveredLoaderFunction] = {
        loader.name: loader for loader in project.loader_functions
    }
    source_names: frozenset[str] = frozenset(source.source_entry.name for source in project.sources)
    entries: dict[str, SourceEntry] = {}
    key: CompiledObjectKey
    for key in selected_keys:
        if key.resource_type != CompiledResourceType.SOURCE:
            continue
        if key.name in entries or key.name in source_names:
            continue
        loader_function: DiscoveredLoaderFunction | None = loader_by_name.get(key.name)
        if loader_function is None or loader_function.name in source_by_loader:
            continue
        entries[key.name] = loader_to_source_entry(project=project, loader=loader_function)
    return entries


def loader_to_source_entry(
    *, project: CompiledProject, loader: DiscoveredLoaderFunction
) -> SourceEntry:
    database: str | None = project.effective_environment_database
    schema: str | None = project.effective_environment_schema
    table: str = f"__loader__{loader.name}"
    if loader.target is not None:
        parts: tuple[str, ...] = tuple(part for part in loader.target.split(".") if part)
        if len(parts) == 1:
            table = parts[0]
        elif len(parts) == 2:
            schema, table = parts
        elif len(parts) == 3:
            database, schema, table = parts
        else:
            table = loader.target
    return SourceEntry(
        name=loader.name,
        database=database,
        schema=schema,
        table=table,
        loader=loader.name,
        write_strategy=loader.write_strategy,
        cursor_column=loader.cursor_column,
        unique_key=loader.unique_key,
        contract=loader.contract,
        meta={"sqlbuild_loader_node": True},
        columns=loader.columns,
    )


def _select_dependency_closure(
    *,
    loader_function: DiscoveredLoaderFunction,
    loader_by_name: dict[str, DiscoveredLoaderFunction],
    loader_name_by_function: dict[object, str],
    source_by_loader: dict[str, SourceEntry],
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> set[CompiledObjectKey]:
    selected: set[CompiledObjectKey] = set()
    dependency_name: str
    for dependency_name in _dependency_loader_names(
        loader_function=loader_function, loader_name_by_function=loader_name_by_function
    ):
        dependency_key: CompiledObjectKey = _loader_node_key(
            loader_name=dependency_name, source_by_loader=source_by_loader
        )
        selected.add(dependency_key)
        dependency_function: DiscoveredLoaderFunction = loader_by_name[dependency_name]
        upstream_deps[dependency_key] = _dependency_keys(
            loader_function=dependency_function,
            loader_name_by_function=loader_name_by_function,
            source_by_loader=source_by_loader,
        )
        selected.update(
            _select_dependency_closure(
                loader_function=dependency_function,
                loader_by_name=loader_by_name,
                loader_name_by_function=loader_name_by_function,
                source_by_loader=source_by_loader,
                upstream_deps=upstream_deps,
            )
        )
    return selected


def _dependency_keys(
    *,
    loader_function: DiscoveredLoaderFunction,
    loader_name_by_function: dict[object, str],
    source_by_loader: dict[str, SourceEntry],
) -> tuple[CompiledObjectKey, ...]:
    return tuple(
        _loader_node_key(loader_name=loader_name, source_by_loader=source_by_loader)
        for loader_name in _dependency_loader_names(
            loader_function=loader_function,
            loader_name_by_function=loader_name_by_function,
        )
    )


def _dependency_loader_names(
    *,
    loader_function: DiscoveredLoaderFunction,
    loader_name_by_function: dict[object, str],
) -> tuple[str, ...]:
    return tuple(loader_name_by_function[dependency] for dependency in loader_function.depends_on)


def _loader_node_key(
    *, loader_name: str, source_by_loader: dict[str, SourceEntry]
) -> CompiledObjectKey:
    source_entry: SourceEntry | None = source_by_loader.get(loader_name)
    return CompiledObjectKey(
        resource_type=CompiledResourceType.SOURCE,
        name=source_entry.name if source_entry is not None else loader_name,
    )
