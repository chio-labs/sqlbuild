"""Public virtual logical target helper."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledRelationDestination
from sqlbuild.virtual.executor.helpers.rewrite import build_virtual_destination


def build_virtual_logical_destination(
    *,
    adapter: BaseAdapter,
    target: CompiledRelationDestination,
    virtual_target_name: str,
    unsuffixed_virtual_target_name: str | None = None,
) -> CompiledRelationDestination:
    """Build the logical virtual target for a model or function."""

    return build_virtual_destination(
        adapter=adapter,
        target=target,
        virtual_target_name=virtual_target_name,
        unsuffixed_virtual_target_name=unsuffixed_virtual_target_name,
    )
