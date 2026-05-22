"""Selection helpers for sqb load source/loader graphs."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction, DiscoveredProjectInputs
from sqlbuild.spec.models.project import EnvironmentConfig
from sqlbuild.spec.models.source import SourceEntry


def select_load_entries(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    environment_config: EnvironmentConfig | None,
) -> tuple[SourceEntry, ...]:
    """Select source and intermediate loader execution entries for sqb load."""

    sources: tuple[SourceEntry, ...] = _environment_sources(
        sources=tuple(
            source
            for source_file in discovered_inputs.source_files
            for source in source_file.source_entries
        ),
        environment_config=environment_config,
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
    upstream_loaders: dict[str, tuple[str, ...]] = {
        loader.name: tuple(loader_name_by_function[dep] for dep in loader.depends_on)
        for loader in discovered_inputs.loader_functions
    }
    source_by_loader: dict[str, tuple[str, ...]] = _source_names_by_loader(managed_sources)

    selected_sources: set[str] = set()
    selected_loaders: set[str] = set()
    raw_selectors: tuple[str, ...] = select or tuple(managed_sources)
    _apply_selectors(
        raw_selectors=raw_selectors,
        selected_sources=selected_sources,
        selected_loaders=selected_loaders,
        managed_sources=managed_sources,
        loaders=loaders,
        source_by_loader=source_by_loader,
        upstream_loaders=upstream_loaders,
    )
    _apply_excludes(
        exclude=exclude,
        selected_sources=selected_sources,
        selected_loaders=selected_loaders,
        managed_sources=managed_sources,
        loaders=loaders,
        source_by_loader=source_by_loader,
        upstream_loaders=upstream_loaders,
    )

    selected_loaders, selected_sources = _prune_missing_dependencies(
        selected_loaders=selected_loaders,
        selected_sources=selected_sources,
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
            entries.append(_loader_to_source_entry(loaders[loader_name], environment_config))
    entries.extend(
        managed_sources[source_name] for source_name in sources_order(sources, selected_sources)
    )
    return tuple(entries)


def sources_order(sources: tuple[SourceEntry, ...], selected_sources: set[str]) -> tuple[str, ...]:
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
    managed_sources: dict[str, SourceEntry],
    loaders: dict[str, DiscoveredLoaderFunction],
    source_by_loader: dict[str, tuple[str, ...]],
    upstream_loaders: dict[str, tuple[str, ...]],
) -> None:
    selector: str
    for selector in raw_selectors:
        name, include_downstream = _parse_load_selector(selector)
        _validate_load_selector(name=name, managed_sources=managed_sources, loaders=loaders)
        _select_name(
            name=name,
            selected_sources=selected_sources,
            selected_loaders=selected_loaders,
            managed_sources=managed_sources,
            source_by_loader=source_by_loader,
            upstream_loaders=upstream_loaders,
        )
        if include_downstream:
            _select_downstream(
                name=name,
                selected_sources=selected_sources,
                selected_loaders=selected_loaders,
                managed_sources=managed_sources,
                loaders=loaders,
                source_by_loader=source_by_loader,
                upstream_loaders=upstream_loaders,
            )


def _apply_excludes(
    *,
    exclude: tuple[str, ...],
    selected_sources: set[str],
    selected_loaders: set[str],
    managed_sources: dict[str, SourceEntry],
    loaders: dict[str, DiscoveredLoaderFunction],
    source_by_loader: dict[str, tuple[str, ...]],
    upstream_loaders: dict[str, tuple[str, ...]],
) -> None:
    selector: str
    for selector in exclude:
        name, include_downstream = _parse_load_selector(selector)
        _validate_load_selector(name=name, managed_sources=managed_sources, loaders=loaders)
        _exclude_name(
            name=name,
            selected_sources=selected_sources,
            selected_loaders=selected_loaders,
            managed_sources=managed_sources,
            source_by_loader=source_by_loader,
        )
        if include_downstream:
            _exclude_downstream(
                name=name,
                selected_sources=selected_sources,
                selected_loaders=selected_loaders,
                managed_sources=managed_sources,
                loaders=loaders,
                source_by_loader=source_by_loader,
                upstream_loaders=upstream_loaders,
            )


def _select_name(
    *,
    name: str,
    selected_sources: set[str],
    selected_loaders: set[str],
    managed_sources: dict[str, SourceEntry],
    source_by_loader: dict[str, tuple[str, ...]],
    upstream_loaders: dict[str, tuple[str, ...]],
) -> None:
    if name in managed_sources:
        selected_sources.add(name)
        selected_loaders.update(
            _upstream_loader_closure(managed_sources[name].loader, upstream_loaders)
        )
        return
    if name in source_by_loader:
        selected_sources.update(source_by_loader[name])
        selected_loaders.update(_upstream_loader_closure(name, upstream_loaders))
        return
    selected_loaders.add(name)
    selected_loaders.update(_upstream_loader_closure(name, upstream_loaders))


def _select_downstream(
    *,
    name: str,
    selected_sources: set[str],
    selected_loaders: set[str],
    managed_sources: dict[str, SourceEntry],
    loaders: dict[str, DiscoveredLoaderFunction],
    source_by_loader: dict[str, tuple[str, ...]],
    upstream_loaders: dict[str, tuple[str, ...]],
) -> None:
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


def _exclude_name(
    *,
    name: str,
    selected_sources: set[str],
    selected_loaders: set[str],
    managed_sources: dict[str, SourceEntry],
    source_by_loader: dict[str, tuple[str, ...]],
) -> None:
    if name in managed_sources:
        selected_sources.discard(name)
        return
    if name in source_by_loader:
        source_name: str
        for source_name in source_by_loader[name]:
            selected_sources.discard(source_name)
        selected_loaders.discard(name)
        return
    selected_loaders.discard(name)


def _exclude_downstream(
    *,
    name: str,
    selected_sources: set[str],
    selected_loaders: set[str],
    managed_sources: dict[str, SourceEntry],
    loaders: dict[str, DiscoveredLoaderFunction],
    source_by_loader: dict[str, tuple[str, ...]],
    upstream_loaders: dict[str, tuple[str, ...]],
) -> None:
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
    *, sources: tuple[SourceEntry, ...], environment_config: EnvironmentConfig | None
) -> tuple[SourceEntry, ...]:
    return tuple(
        replace(
            source,
            database=source.database
            if source.database is not None or environment_config is None
            else environment_config.database,
            schema=source.schema
            if source.schema is not None or environment_config is None
            else environment_config.schema,
        )
        for source in sources
    )


def _loader_to_source_entry(
    loader: DiscoveredLoaderFunction,
    environment_config: EnvironmentConfig | None,
) -> SourceEntry:
    database: str | None = environment_config.database if environment_config is not None else None
    schema: str | None = environment_config.schema if environment_config is not None else None
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


def _parse_load_selector(selector: str) -> tuple[str, bool]:
    stripped: str = selector.strip()
    include_downstream: bool = stripped.endswith("+")
    name: str = stripped.strip("+")
    return name, include_downstream


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
    loader_name: str | None,
    upstream_loaders: dict[str, tuple[str, ...]],
) -> set[str]:
    if loader_name is None:
        return set()
    result: set[str] = {loader_name}
    dependency: str
    for dependency in upstream_loaders.get(loader_name, ()):
        result.update(_upstream_loader_closure(dependency, upstream_loaders))
    return result


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
) -> tuple[set[str], set[str]]:
    pruned_loaders: set[str] = set(selected_loaders)
    pruned_sources: set[str] = set(selected_sources)
    changed: bool = True
    while changed:
        changed = False
        loader_name: str
        for loader_name in tuple(pruned_loaders):
            if _has_missing_loader_dependency(
                loader_name=loader_name,
                selected_loaders=pruned_loaders,
                upstream_loaders=upstream_loaders,
            ):
                pruned_loaders.remove(loader_name)
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
) -> bool:
    dependencies: tuple[str, ...] = upstream_loaders[loader_name]
    return any(dependency not in selected_loaders for dependency in dependencies)


def _topological_loader_order(
    *, loader_names: set[str], upstream_loaders: dict[str, tuple[str, ...]]
) -> tuple[str, ...]:
    ordered: list[str] = []
    visited: set[str] = set()

    def visit(loader_name: str) -> None:
        if loader_name in visited:
            return
        dependency: str
        for dependency in upstream_loaders.get(loader_name, ()):
            if dependency in loader_names:
                visit(dependency)
        visited.add(loader_name)
        ordered.append(loader_name)

    for loader_name in sorted(loader_names):
        visit(loader_name)
    return tuple(ordered)
