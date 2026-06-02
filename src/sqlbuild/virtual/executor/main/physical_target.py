"""Public virtual physical target helper."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledRelationDestination
from sqlbuild.virtual.executor.helpers.rewrite import build_physical_destination


def build_virtual_physical_destination(
    *,
    adapter: BaseAdapter,
    target: CompiledRelationDestination,
    model_name: str,
    version_hash: str,
) -> CompiledRelationDestination:
    """Build the physical virtual-version target for a model."""

    return build_physical_destination(
        adapter=adapter,
        target=target,
        model_name=model_name,
        version_hash=version_hash,
    )
