"""Native project graph construction and its Python dict views."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.graph.models import LineageGraphViews
from sqlbuild.compiler.graph.types import NativeKey


class _KeyCache:
    """One `CompiledObjectKey` per native pair, so shared keys convert once."""

    def __init__(self) -> None:
        self._keys: dict[NativeKey, CompiledObjectKey] = {}

    def key(self, pair: NativeKey) -> CompiledObjectKey:
        existing: CompiledObjectKey | None = self._keys.get(pair)
        if existing is not None:
            return existing
        created: CompiledObjectKey = CompiledObjectKey(
            resource_type=CompiledResourceType(pair[0]), name=pair[1]
        )
        self._keys[pair] = created
        return created

    def keys(self, pairs: Iterable[NativeKey]) -> tuple[CompiledObjectKey, ...]:
        return tuple(self.key(pair) for pair in pairs)


def native_key(key: CompiledObjectKey) -> NativeKey:
    """The `(resource type, name)` pair the native graph keys resources by."""

    return (str(key.resource_type), key.name)


def native_keys(keys: Iterable[CompiledObjectKey]) -> list[NativeKey]:
    """Native pairs for `keys`, in order."""

    return [native_key(key) for key in keys]


def build_native_project_graph_impl(project: CompiledProject) -> _native.NativeProjectGraph:
    """The project's native graph, built once per compiled project."""

    return project.lineage_graph


def project_lineage_views_impl(project: CompiledProject) -> LineageGraphViews:
    """The project's lineage edges and selector indexes as fresh dicts."""

    return lineage_graph_views_impl(project.lineage_graph)


def native_graph_from_views_impl(
    *,
    all_keys: Mapping[str, CompiledObjectKey],
    upstream: Mapping[CompiledObjectKey, Iterable[CompiledObjectKey]],
    downstream: Mapping[CompiledObjectKey, Iterable[CompiledObjectKey]],
    tag_index: Mapping[str, Iterable[CompiledObjectKey]],
    path_index: Mapping[CompiledObjectKey, str],
) -> _native.NativeProjectGraph:
    """A native graph over dict indexes a caller built, keeping their order."""

    return _native.NativeProjectGraph.from_indexes(
        (
            [(name, native_key(key)) for name, key in all_keys.items()],
            [(native_key(key), native_keys(deps)) for key, deps in upstream.items()],
            [(native_key(key), native_keys(deps)) for key, deps in downstream.items()],
            [(tag, native_keys(keys)) for tag, keys in tag_index.items()],
            [(native_key(key), folder) for key, folder in path_index.items()],
        )
    )


def lineage_graph_views_impl(graph: _native.NativeProjectGraph) -> LineageGraphViews:
    """The native graph's indexes as the dicts Python graph consumers read."""

    keys: _KeyCache = _KeyCache()
    names, upstream, downstream, tags, paths = graph.indexes()
    return LineageGraphViews(
        upstream_deps={keys.key(key): keys.keys(deps) for key, deps in upstream},
        downstream_deps={keys.key(key): keys.keys(deps) for key, deps in downstream},
        tag_index={tag: frozenset(keys.keys(tagged)) for tag, tagged in tags},
        path_index={keys.key(key): folder for key, folder in paths},
        all_keys={name: keys.key(key) for name, key in names},
    )


def lineage_graph_names_impl(graph: _native.NativeProjectGraph) -> dict[str, CompiledObjectKey]:
    """Selector name to key, converted from the native names only."""

    keys: _KeyCache = _KeyCache()
    return {name: keys.key(key) for name, key in graph.names()}


def python_keys(keys: Iterable[NativeKey]) -> frozenset[CompiledObjectKey]:
    """`CompiledObjectKey`s for native pairs."""

    cache: _KeyCache = _KeyCache()
    return frozenset(cache.keys(keys))
