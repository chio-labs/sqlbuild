"""Loader DAG planning helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.spec.contracts.models import SourceEntry


def expand_selected_loader_dependencies(
    *,
    project: CompiledProject,
    selected_keys: frozenset[CompiledObjectKey],
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    executable_dependency_source_keys: frozenset[CompiledObjectKey] = frozenset(),
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
        if source_entry is None:
            if selected_key.name in loader_by_name:
                expanded_upstream.setdefault(selected_key, ())
            continue
        if source_entry.loader is None:
            continue
        loader_function: DiscoveredLoaderFunction | None = loader_by_name.get(source_entry.loader)
        if loader_function is None:
            continue
        expanded_upstream[selected_key] = _dependency_keys(
            loader_function=loader_function,
            loader_name_by_function=loader_name_by_function,
            source_by_loader=source_by_loader,
        )
        expanded_upstream.update(
            _dependency_closure_edges(
                loader_function=loader_function,
                loader_by_name=loader_by_name,
                loader_name_by_function=loader_name_by_function,
                source_by_loader=source_by_loader,
            )
        )
        if selected_key not in executable_dependency_source_keys:
            continue
        dependency_loader_name: str
        for dependency_loader_name in upstream_loader_dependency_names(
            loader_function=loader_function,
            loader_functions=project.loader_functions,
        ):
            expanded_selected.add(
                _loader_node_key(
                    loader_name=dependency_loader_name,
                    source_by_loader=source_by_loader,
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


def build_upstream_intermediate_source_map(
    *, project: CompiledProject, selected_keys: frozenset[CompiledObjectKey]
) -> dict[str, SourceEntry]:
    """Return synthetic source entries for upstream intermediate loaders of selected sources."""

    loader_by_name: dict[str, DiscoveredLoaderFunction] = {
        loader.name: loader for loader in project.loader_functions
    }
    source_by_name: dict[str, SourceEntry] = {
        source.source_entry.name: source.source_entry for source in project.sources
    }
    source_by_loader: dict[str, SourceEntry] = {
        source.source_entry.loader: source.source_entry
        for source in project.sources
        if source.source_entry.loader is not None
    }
    entries: dict[str, SourceEntry] = {}
    key: CompiledObjectKey
    for key in selected_keys:
        if key.resource_type != CompiledResourceType.SOURCE:
            continue
        source_entry: SourceEntry | None = source_by_name.get(key.name)
        if source_entry is None or source_entry.loader is None:
            continue
        loader_function: DiscoveredLoaderFunction | None = loader_by_name.get(source_entry.loader)
        if loader_function is None:
            continue
        dependency_name: str
        for dependency_name in upstream_loader_dependency_names(
            loader_function=loader_function,
            loader_functions=project.loader_functions,
        ):
            if dependency_name in source_by_loader:
                continue
            dependency_loader: DiscoveredLoaderFunction | None = loader_by_name.get(dependency_name)
            if dependency_loader is None:
                continue
            entries.setdefault(
                dependency_name,
                loader_to_source_entry(project=project, loader=dependency_loader),
            )
    return entries


def upstream_loader_dependency_names(
    *,
    loader_function: DiscoveredLoaderFunction,
    loader_functions: tuple[DiscoveredLoaderFunction, ...],
) -> tuple[str, ...]:
    """Return upstream loader dependency names for one loader function."""

    loader_by_name: dict[str, DiscoveredLoaderFunction] = {
        loader.name: loader for loader in loader_functions
    }
    loader_name_by_function: dict[object, str] = {
        loader.function: loader.name for loader in loader_functions
    }
    names: list[str] = []
    pending: list[str] = list(
        _dependency_loader_names(
            loader_function=loader_function,
            loader_name_by_function=loader_name_by_function,
        )
    )
    while pending:
        current: str = pending.pop(0)
        if current in names:
            continue
        names.append(current)
        dependency_loader: DiscoveredLoaderFunction | None = loader_by_name.get(current)
        if dependency_loader is None:
            continue
        pending.extend(
            _dependency_loader_names(
                loader_function=dependency_loader,
                loader_name_by_function=loader_name_by_function,
            )
        )
    return tuple(names)


def loader_to_source_entry(
    *, project: CompiledProject, loader: DiscoveredLoaderFunction
) -> SourceEntry:
    database: str | None = project.effective_target_database
    schema: str | None = project.effective_target_schema
    table: str = f"__loader__{loader.name}"
    if loader.destination is not None:
        parts: tuple[str, ...] = tuple(part for part in loader.destination.split(".") if part)
        if len(parts) == 1:
            table = parts[0]
        source_name_part_count: int = 2
        qualified_source_name_part_count: int = 3
        if len(parts) == source_name_part_count:
            schema, table = parts
        elif len(parts) == qualified_source_name_part_count:
            database, schema, table = parts
        else:
            table = loader.destination
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


def _dependency_closure_edges(
    *,
    loader_function: DiscoveredLoaderFunction,
    loader_by_name: dict[str, DiscoveredLoaderFunction],
    loader_name_by_function: dict[object, str],
    source_by_loader: dict[str, SourceEntry],
) -> dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]:
    edges: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = {}
    dependency_name: str
    for dependency_name in _dependency_loader_names(
        loader_function=loader_function, loader_name_by_function=loader_name_by_function
    ):
        dependency_key: CompiledObjectKey = _loader_node_key(
            loader_name=dependency_name, source_by_loader=source_by_loader
        )
        dependency_function: DiscoveredLoaderFunction = loader_by_name[dependency_name]
        edges[dependency_key] = _dependency_keys(
            loader_function=dependency_function,
            loader_name_by_function=loader_name_by_function,
            source_by_loader=source_by_loader,
        )
        edges.update(
            _dependency_closure_edges(
                loader_function=dependency_function,
                loader_by_name=loader_by_name,
                loader_name_by_function=loader_name_by_function,
                source_by_loader=source_by_loader,
            )
        )
    return edges


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
    return tuple(
        loader_name_by_function[dependency]
        for dependency in loader_function.depends_on
        if dependency in loader_name_by_function
    )


def _loader_node_key(
    *, loader_name: str, source_by_loader: dict[str, SourceEntry]
) -> CompiledObjectKey:
    source_entry: SourceEntry | None = source_by_loader.get(loader_name)
    return CompiledObjectKey(
        resource_type=CompiledResourceType.SOURCE,
        name=source_entry.name if source_entry is not None else loader_name,
    )
