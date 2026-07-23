"""Selection helpers for sqb load source/loader graphs."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import LoadSelectionSets, LoadSelectorSets
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction, DiscoveredProjectInputs
from sqlbuild.compiler.graph.main.transitive_closure import transitive_closure
from sqlbuild.spec.contracts.models import SourceEntry, TargetConfig


def select_load_entries(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    target_config: TargetConfig | None,
) -> tuple[SourceEntry, ...]:
    """Select source and intermediate loader execution entries for sqb load."""

    discovered_sources: list[SourceEntry] = []
    for source_file in discovered_inputs.source_files:
        discovered_sources.extend(source_file.source_entries)
    sources: tuple[SourceEntry, ...] = _environment_sources(
        sources=tuple(discovered_sources), target_config=target_config
    )
    managed_sources: dict[str, SourceEntry] = {
        source.name: source for source in sources if source.loader is not None
    }
    loaders: dict[str, DiscoveredLoaderFunction] = {
        loader.name: loader for loader in discovered_inputs.loader_functions
    }
    loader_name_by_function: dict[object, str] = {
        loader.function: loader.name for loader in discovered_inputs.loader_functions
    }
    upstream_loaders: dict[str, tuple[str, ...]] = {}
    for loader in discovered_inputs.loader_functions:
        dependency_names: list[str] = []
        for dependency in loader.depends_on:
            if dependency in loader_name_by_function:
                dependency_names.append(loader_name_by_function[dependency])
        upstream_loaders[loader.name] = tuple(dependency_names)
    source_by_loader: dict[str, tuple[str, ...]] = _source_names_by_loader(managed_sources)

    selected_sources: set[str] = set()
    selected_loaders: set[str] = set()
    directly_selected_loaders: set[str] = set()
    raw_selectors: tuple[str, ...] = select or tuple(f"+{name}" for name in managed_sources)
    selector_sets: LoadSelectorSets = _apply_selectors(
        raw_selectors=raw_selectors,
        selected_sources=selected_sources,
        selected_loaders=selected_loaders,
        directly_selected_loaders=directly_selected_loaders,
        managed_sources=managed_sources,
        loaders=loaders,
        source_by_loader=source_by_loader,
        upstream_loaders=upstream_loaders,
    )
    selected_sources = selector_sets.selected_sources
    selected_loaders = selector_sets.selected_loaders
    directly_selected_loaders = selector_sets.directly_selected_loaders
    exclusion_sets, excluded_loaders = _apply_excludes(
        exclude=exclude,
        selected_sources=selected_sources,
        selected_loaders=selected_loaders,
        managed_sources=managed_sources,
        loaders=loaders,
        source_by_loader=source_by_loader,
        upstream_loaders=upstream_loaders,
    )
    selected_sources = exclusion_sets.selected_sources
    selected_loaders = exclusion_sets.selected_loaders

    selected_loaders, selected_sources = _prune_missing_dependencies(
        selected_loaders=selected_loaders,
        selected_sources=selected_sources,
        managed_sources=managed_sources,
        upstream_loaders=upstream_loaders,
        excluded_loaders=excluded_loaders,
    )
    selected_loaders = _prune_unneeded_loaders(
        selected_loaders=selected_loaders,
        selected_sources=selected_sources,
        directly_selected_loaders=directly_selected_loaders,
        managed_sources=managed_sources,
        upstream_loaders=upstream_loaders,
    )

    entries: list[SourceEntry] = []
    selected_terminal_loaders: set[str | None] = {
        managed_sources[source_name].loader for source_name in selected_sources
    }
    loader_name: str
    for loader_name in _topological_loader_order(
        loader_names=selected_loaders,
        upstream_loaders=upstream_loaders,
    ):
        if loader_name not in selected_terminal_loaders:
            entries.append(
                _loader_to_source_entry(loader=loaders[loader_name], target_config=target_config)
            )
    entries.extend(
        managed_sources[source_name]
        for source_name in sources_order(sources=sources, selected_sources=selected_sources)
    )
    return tuple(entries)


def select_load_reference_entries(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    selected_sources: tuple[SourceEntry, ...],
    target_config: TargetConfig | None,
) -> tuple[SourceEntry, ...]:
    """Return unselected upstream intermediate loader entries used only for refs."""

    selected_names: frozenset[str] = frozenset(source.name for source in selected_sources)
    loaders: dict[str, DiscoveredLoaderFunction] = {
        loader.name: loader for loader in discovered_inputs.loader_functions
    }
    loader_name_by_function: dict[object, str] = {
        loader.function: loader.name for loader in discovered_inputs.loader_functions
    }
    upstream_loaders: dict[str, tuple[str, ...]] = {}
    for loader in discovered_inputs.loader_functions:
        dependency_names: list[str] = []
        for dependency in loader.depends_on:
            if dependency in loader_name_by_function:
                dependency_names.append(loader_name_by_function[dependency])
        upstream_loaders[loader.name] = tuple(dependency_names)
    reference_loader_names: set[str] = set()
    source: SourceEntry
    for source in selected_sources:
        if source.loader is None or source.loader not in upstream_loaders:
            continue
        dependency_name: str
        for dependency_name in upstream_loaders[source.loader]:
            reference_loader_names.update(
                _upstream_loader_closure(
                    loader_name=dependency_name, upstream_loaders=upstream_loaders
                )
            )
    return tuple(
        _loader_to_source_entry(loader=loaders[loader_name], target_config=target_config)
        for loader_name in _topological_loader_order(
            loader_names=reference_loader_names,
            upstream_loaders=upstream_loaders,
        )
        if loader_name in loaders and loader_name not in selected_names
    )


def sources_order(
    *, sources: tuple[SourceEntry, ...], selected_sources: set[str]
) -> tuple[str, ...]:
    return tuple(source.name for source in sources if source.name in selected_sources)


def _source_names_by_loader(managed_sources: dict[str, SourceEntry]) -> dict[str, tuple[str, ...]]:
    grouped_source_names: dict[str, list[str]] = {}
    source: SourceEntry
    for source in managed_sources.values():
        if source.loader is None:
            continue
        grouped_source_names.setdefault(source.loader, []).append(source.name)
    return {
        loader_name: tuple(source_names)
        for loader_name, source_names in grouped_source_names.items()
    }


def _apply_selectors(
    *,
    raw_selectors: tuple[str, ...],
    selected_sources: set[str],
    selected_loaders: set[str],
    directly_selected_loaders: set[str],
    managed_sources: dict[str, SourceEntry],
    loaders: dict[str, DiscoveredLoaderFunction],
    source_by_loader: dict[str, tuple[str, ...]],
    upstream_loaders: dict[str, tuple[str, ...]],
) -> LoadSelectorSets:
    selector: str
    for selector in raw_selectors:
        name, include_upstream, include_downstream = _parse_load_selector(selector)
        _validate_load_selector(name=name, managed_sources=managed_sources, loaders=loaders)
        selector_sets: LoadSelectorSets = _select_name(
            name=name,
            include_upstream=include_upstream,
            selected_sources=selected_sources,
            selected_loaders=selected_loaders,
            directly_selected_loaders=directly_selected_loaders,
            managed_sources=managed_sources,
            loaders=loaders,
            source_by_loader=source_by_loader,
            upstream_loaders=upstream_loaders,
        )
        selected_sources = selector_sets.selected_sources
        selected_loaders = selector_sets.selected_loaders
        directly_selected_loaders = selector_sets.directly_selected_loaders
        if include_downstream:
            selection_sets: LoadSelectionSets = _select_downstream(
                name=name,
                selected_sources=selected_sources,
                selected_loaders=selected_loaders,
                managed_sources=managed_sources,
                loaders=loaders,
                source_by_loader=source_by_loader,
                upstream_loaders=upstream_loaders,
            )
            selected_sources = selection_sets.selected_sources
            selected_loaders = selection_sets.selected_loaders
    return LoadSelectorSets(selected_sources, selected_loaders, directly_selected_loaders)


def _apply_excludes(
    *,
    exclude: tuple[str, ...],
    selected_sources: set[str],
    selected_loaders: set[str],
    managed_sources: dict[str, SourceEntry],
    loaders: dict[str, DiscoveredLoaderFunction],
    source_by_loader: dict[str, tuple[str, ...]],
    upstream_loaders: dict[str, tuple[str, ...]],
) -> tuple[LoadSelectionSets, set[str]]:
    excluded_loaders: set[str] = set()
    selector: str
    for selector in exclude:
        name, _, include_downstream = _parse_load_selector(selector)
        _validate_load_selector(name=name, managed_sources=managed_sources, loaders=loaders)
        selection_sets: LoadSelectionSets
        selection_sets, excluded_loaders = _exclude_name(
            name=name,
            selected_sources=selected_sources,
            selected_loaders=selected_loaders,
            managed_sources=managed_sources,
            loaders=loaders,
            source_by_loader=source_by_loader,
            excluded_loaders=excluded_loaders,
        )
        selected_sources = selection_sets.selected_sources
        selected_loaders = selection_sets.selected_loaders
        if include_downstream:
            selection_sets = _exclude_downstream(
                name=name,
                selected_sources=selected_sources,
                selected_loaders=selected_loaders,
                managed_sources=managed_sources,
                loaders=loaders,
                source_by_loader=source_by_loader,
                upstream_loaders=upstream_loaders,
            )
            selected_sources = selection_sets.selected_sources
            selected_loaders = selection_sets.selected_loaders
    return LoadSelectionSets(selected_sources, selected_loaders), excluded_loaders


def _select_name(
    *,
    name: str,
    include_upstream: bool,
    selected_sources: set[str],
    selected_loaders: set[str],
    directly_selected_loaders: set[str],
    managed_sources: dict[str, SourceEntry],
    loaders: dict[str, DiscoveredLoaderFunction],
    source_by_loader: dict[str, tuple[str, ...]],
    upstream_loaders: dict[str, tuple[str, ...]],
) -> LoadSelectorSets:
    if name in managed_sources:
        selected_sources.add(name)
        loader_name: str | None = managed_sources[name].loader
        if loader_name is not None:
            selected_loaders.add(loader_name)
            if include_upstream:
                selected_loaders.update(
                    _upstream_loader_closure(
                        loader_name=loader_name, upstream_loaders=upstream_loaders
                    )
                )
        return LoadSelectorSets(selected_sources, selected_loaders, directly_selected_loaders)
    if name in source_by_loader:
        selected_sources.update(source_by_loader[name])
        selected_loaders.add(name)
        if include_upstream:
            selected_loaders.update(
                _upstream_loader_closure(loader_name=name, upstream_loaders=upstream_loaders)
            )
        return LoadSelectorSets(selected_sources, selected_loaders, directly_selected_loaders)
    if name in loaders:
        selected_loaders.add(name)
        directly_selected_loaders.add(name)
        if include_upstream:
            selected_loaders.update(
                _upstream_loader_closure(loader_name=name, upstream_loaders=upstream_loaders)
            )
    return LoadSelectorSets(selected_sources, selected_loaders, directly_selected_loaders)


def _select_downstream(
    *,
    name: str,
    selected_sources: set[str],
    selected_loaders: set[str],
    managed_sources: dict[str, SourceEntry],
    loaders: dict[str, DiscoveredLoaderFunction],
    source_by_loader: dict[str, tuple[str, ...]],
    upstream_loaders: dict[str, tuple[str, ...]],
) -> LoadSelectionSets:
    downstream_loaders, downstream_sources = _downstream_closure(
        loader_name=_selected_loader_name(
            name=name,
            managed_sources=managed_sources,
            loaders=loaders,
        ),
        upstream_loaders=upstream_loaders,
        source_by_loader=source_by_loader,
    )
    selected_loaders.update(downstream_loaders)
    selected_sources.update(downstream_sources)
    return LoadSelectionSets(selected_sources, selected_loaders)


def _exclude_name(
    *,
    name: str,
    selected_sources: set[str],
    selected_loaders: set[str],
    managed_sources: dict[str, SourceEntry],
    loaders: dict[str, DiscoveredLoaderFunction],
    source_by_loader: dict[str, tuple[str, ...]],
    excluded_loaders: set[str],
) -> tuple[LoadSelectionSets, set[str]]:
    if name in managed_sources:
        selected_sources.discard(name)
        loader_name: str | None = managed_sources[name].loader
        if loader_name is not None and not any(
            source_name in selected_sources for source_name in source_by_loader.get(loader_name, ())
        ):
            selected_loaders.discard(loader_name)
        return LoadSelectionSets(selected_sources, selected_loaders), excluded_loaders
    if name in source_by_loader:
        source_name: str
        for source_name in source_by_loader[name]:
            selected_sources.discard(source_name)
        selected_loaders.discard(name)
        excluded_loaders.add(name)
        return LoadSelectionSets(selected_sources, selected_loaders), excluded_loaders
    if name in loaders:
        selected_loaders.discard(name)
        excluded_loaders.add(name)
    return LoadSelectionSets(selected_sources, selected_loaders), excluded_loaders


def _exclude_downstream(
    *,
    name: str,
    selected_sources: set[str],
    selected_loaders: set[str],
    managed_sources: dict[str, SourceEntry],
    loaders: dict[str, DiscoveredLoaderFunction],
    source_by_loader: dict[str, tuple[str, ...]],
    upstream_loaders: dict[str, tuple[str, ...]],
) -> LoadSelectionSets:
    downstream_loaders, downstream_sources = _downstream_closure(
        loader_name=_selected_loader_name(
            name=name,
            managed_sources=managed_sources,
            loaders=loaders,
        ),
        upstream_loaders=upstream_loaders,
        source_by_loader=source_by_loader,
    )
    selected_loaders.difference_update(downstream_loaders)
    selected_sources.difference_update(downstream_sources)
    return LoadSelectionSets(selected_sources, selected_loaders)


def _selected_loader_name(
    *,
    name: str,
    managed_sources: dict[str, SourceEntry],
    loaders: dict[str, DiscoveredLoaderFunction],
) -> str | None:
    if name in loaders:
        return name
    return managed_sources[name].loader


def _environment_sources(
    *, sources: tuple[SourceEntry, ...], target_config: TargetConfig | None
) -> tuple[SourceEntry, ...]:
    return tuple(
        replace(
            source,
            database=source.database
            if source.database is not None or target_config is None
            else target_config.database,
            schema=source.schema
            if source.schema is not None or target_config is None
            else target_config.schema,
        )
        for source in sources
    )


def _loader_to_source_entry(
    *,
    loader: DiscoveredLoaderFunction,
    target_config: TargetConfig | None,
) -> SourceEntry:
    database: str | None = target_config.database if target_config is not None else None
    schema: str | None = target_config.schema if target_config is not None else None
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


def _parse_load_selector(selector: str) -> tuple[str, bool, bool]:
    stripped: str = selector.strip()
    include_upstream: bool = stripped.startswith("+")
    include_downstream: bool = stripped.endswith("+")
    name: str = stripped.strip("+")
    return name, include_upstream, include_downstream


def _validate_load_selector(
    *,
    name: str,
    managed_sources: dict[str, SourceEntry],
    loaders: dict[str, DiscoveredLoaderFunction],
) -> None:
    if name in managed_sources or name in loaders:
        return
    raise CliUserError(
        f"sqb load selector '{name}' does not match any managed source or loader",
        code="C901",
        help="Use exact managed source names or loader function names.",
    )


def _upstream_loader_closure(
    *,
    loader_name: str | None,
    upstream_loaders: dict[str, tuple[str, ...]],
) -> set[str]:
    if loader_name is None:
        return set()
    return {loader_name, *transitive_closure(start=loader_name, edges=upstream_loaders)}


def _downstream_closure(
    *,
    loader_name: str | None,
    upstream_loaders: dict[str, tuple[str, ...]],
    source_by_loader: dict[str, tuple[str, ...]],
) -> tuple[set[str], set[str]]:
    if loader_name is None:
        return set(), set()
    loaders: set[str] = {loader_name}
    sources: set[str] = set(source_by_loader.get(loader_name, ()))
    downstream_loader: str
    deps: tuple[str, ...]
    for downstream_loader, deps in upstream_loaders.items():
        if loader_name not in deps:
            continue
        next_loaders, next_sources = _downstream_closure(
            loader_name=downstream_loader,
            upstream_loaders=upstream_loaders,
            source_by_loader=source_by_loader,
        )
        loaders.update(next_loaders)
        sources.update(next_sources)
    return loaders, sources


def _prune_missing_dependencies(
    *,
    selected_loaders: set[str],
    selected_sources: set[str],
    managed_sources: dict[str, SourceEntry],
    upstream_loaders: dict[str, tuple[str, ...]],
    excluded_loaders: set[str],
) -> tuple[set[str], set[str]]:
    pruned_loaders: set[str] = set(selected_loaders)
    pruned_sources: set[str] = set(selected_sources)
    blocked_loaders: set[str] = set(excluded_loaders)
    changed: bool = True
    while changed:
        changed = False
        loader_name: str
        for loader_name in tuple(pruned_loaders):
            if _has_missing_loader_dependency(
                loader_name=loader_name,
                selected_loaders=pruned_loaders,
                upstream_loaders=upstream_loaders,
                blocked_loaders=blocked_loaders,
            ):
                pruned_loaders.remove(loader_name)
                blocked_loaders.add(loader_name)
                changed = True
        source_name: str
        for source_name in tuple(pruned_sources):
            source_loader: str | None = managed_sources[source_name].loader
            if source_loader is not None and source_loader not in pruned_loaders:
                pruned_sources.remove(source_name)
                changed = True
    return pruned_loaders, pruned_sources


def _has_missing_loader_dependency(
    *,
    loader_name: str,
    selected_loaders: set[str],
    upstream_loaders: dict[str, tuple[str, ...]],
    blocked_loaders: set[str],
) -> bool:
    dependencies: tuple[str, ...] = upstream_loaders[loader_name]
    return any(
        dependency not in selected_loaders and dependency in blocked_loaders
        for dependency in dependencies
    )


def _prune_unneeded_loaders(
    *,
    selected_loaders: set[str],
    selected_sources: set[str],
    directly_selected_loaders: set[str],
    managed_sources: dict[str, SourceEntry],
    upstream_loaders: dict[str, tuple[str, ...]],
) -> set[str]:
    needed_loaders: set[str] = set(directly_selected_loaders)
    source_name: str
    for source_name in selected_sources:
        source_loader: str | None = managed_sources[source_name].loader
        if source_loader is not None and source_loader in selected_loaders:
            needed_loaders.add(source_loader)

    changed: bool = True
    while changed:
        changed = False
        loader_name: str
        for loader_name in tuple(needed_loaders):
            dependency_name: str
            for dependency_name in upstream_loaders.get(loader_name, ()):
                if dependency_name in selected_loaders and dependency_name not in needed_loaders:
                    needed_loaders.add(dependency_name)
                    changed = True

    return selected_loaders.intersection(needed_loaders)


def _topological_loader_order(
    *, loader_names: set[str], upstream_loaders: dict[str, tuple[str, ...]]
) -> tuple[str, ...]:
    ordered: tuple[str, ...] = ()
    visited: frozenset[str] = frozenset()
    for loader_name in sorted(loader_names):
        ordered, visited = _visit_loader(
            loader_name=loader_name,
            loader_names=loader_names,
            upstream_loaders=upstream_loaders,
            ordered=ordered,
            visited=visited,
        )
    return ordered


def _visit_loader(
    *,
    loader_name: str,
    loader_names: set[str],
    upstream_loaders: dict[str, tuple[str, ...]],
    ordered: tuple[str, ...],
    visited: frozenset[str],
) -> tuple[tuple[str, ...], frozenset[str]]:
    if loader_name in visited:
        return ordered, visited
    dependency: str
    for dependency in upstream_loaders.get(loader_name, ()):
        if dependency in loader_names:
            ordered, visited = _visit_loader(
                loader_name=dependency,
                loader_names=loader_names,
                upstream_loaders=upstream_loaders,
                ordered=ordered,
                visited=visited,
            )
    return (*ordered, loader_name), visited | {loader_name}
