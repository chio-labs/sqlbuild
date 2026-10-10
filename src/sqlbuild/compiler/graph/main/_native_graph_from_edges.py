"""Native graph over caller-built edge maps alone."""

from collections.abc import Iterable, Mapping

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.graph._helpers.native_graph import native_graph_from_views_impl


def native_graph_from_edges(
    *,
    upstream: Mapping[CompiledObjectKey, Iterable[CompiledObjectKey]],
    downstream: Mapping[CompiledObjectKey, Iterable[CompiledObjectKey]],
) -> _native.NativeProjectGraph:
    """Return a native graph holding these edges in their order, with no selector indexes."""

    return native_graph_from_views_impl(
        all_keys={}, upstream=upstream, downstream=downstream, tag_index={}, path_index={}
    )
