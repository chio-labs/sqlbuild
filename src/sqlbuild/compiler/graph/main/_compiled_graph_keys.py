"""Conversion of the native graph's key pairs to compiled keys."""

from collections.abc import Iterable

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.graph._helpers.native_graph import python_keys
from sqlbuild.compiler.graph.types import NativeKey


def compiled_graph_keys(keys: Iterable[NativeKey]) -> frozenset[CompiledObjectKey]:
    """Return `CompiledObjectKey`s for native graph key pairs."""

    return python_keys(keys)
