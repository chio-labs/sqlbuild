"""Graph keys for typed SQL resource references."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind

_RESOURCE_TYPE_BY_REF_KIND: dict[SqlResourceRefKind, CompiledResourceType] = {
    SqlResourceRefKind.MODEL: CompiledResourceType.MODEL,
    SqlResourceRefKind.SOURCE: CompiledResourceType.SOURCE,
    SqlResourceRefKind.SEED: CompiledResourceType.SEED,
}


def sql_ref_key_impl(ref: SqlResourceRef) -> CompiledObjectKey:
    """Return the compiled graph key a typed SQL reference names."""

    return CompiledObjectKey(resource_type=_RESOURCE_TYPE_BY_REF_KIND[ref.kind], name=ref.name)
