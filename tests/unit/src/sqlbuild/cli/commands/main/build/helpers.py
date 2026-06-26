from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType


def build_compiled_object_key(
    resource_type: CompiledResourceType,
    name: str,
) -> CompiledObjectKey:
    return CompiledObjectKey(resource_type=resource_type, name=name)
