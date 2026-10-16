from __future__ import annotations

from sqlbuild._native import CompiledObjectKey, CompiledResourceType


def build_compiled_object_key(
    resource_type: CompiledResourceType,
    name: str,
) -> CompiledObjectKey:
    return CompiledObjectKey(resource_type=resource_type, name=name)
