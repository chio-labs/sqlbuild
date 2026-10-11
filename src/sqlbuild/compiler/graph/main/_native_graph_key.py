"""Conversion of one compiled key to the native graph's key pair."""

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.graph._helpers.native_graph import native_key
from sqlbuild.compiler.graph.types import NativeKey


def native_graph_key(key: CompiledObjectKey) -> NativeKey:
    """Return the native graph's `(resource type, name)` pair for `key`."""

    return native_key(key)
