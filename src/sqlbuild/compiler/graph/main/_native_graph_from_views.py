"""Native project graph over caller-built dict indexes."""

from collections.abc import Iterable, Mapping

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.graph._helpers.native_graph import native_graph_from_views_impl


def native_graph_from_views(
    *,
    all_keys: Mapping[str, CompiledObjectKey],
    upstream: Mapping[CompiledObjectKey, Iterable[CompiledObjectKey]],
    downstream: Mapping[CompiledObjectKey, Iterable[CompiledObjectKey]],
    tag_index: Mapping[str, Iterable[CompiledObjectKey]],
    path_index: Mapping[CompiledObjectKey, str],
) -> _native.NativeProjectGraph:
    """Return a native graph over these indexes, keeping their order."""

    return native_graph_from_views_impl(
        all_keys=all_keys,
        upstream=upstream,
        downstream=downstream,
        tag_index=tag_index,
        path_index=path_index,
    )
