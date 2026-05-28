"""Public virtual physical target helper."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledRelationTarget
from sqlbuild.virtual.executor.helpers.rewrite import build_physical_target


def build_virtual_physical_target(
    *,
    adapter: BaseAdapter,
    target: CompiledRelationTarget,
    model_name: str,
    version_hash: str,
) -> CompiledRelationTarget:
    """Build the physical virtual-version target for a model."""

    return build_physical_target(
        adapter=adapter,
        target=target,
        model_name=model_name,
        version_hash=version_hash,
    )
