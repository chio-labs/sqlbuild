"""Conversion of compiled keys to the native graph's key pairs."""

from collections.abc import Iterable

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.graph._helpers.native_graph import native_keys
from sqlbuild.compiler.graph.types import NativeKey


def native_graph_keys(keys: Iterable[CompiledObjectKey]) -> list[NativeKey]:
    """Return the native graph's `(resource type, name)` pairs for `keys`, in order."""

    return native_keys(keys)
