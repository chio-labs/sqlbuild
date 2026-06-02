"""Public virtual target construction entrypoint."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledRelationDestination
from sqlbuild.virtual.executor.helpers.rewrite import (
    build_virtual_destination as _build_virtual_destination,
)


def build_virtual_destination(
    *,
    adapter: BaseAdapter,
    target: CompiledRelationDestination,
    virtual_environment_name: str,
    unsuffixed_virtual_environment_name: str | None = None,
) -> CompiledRelationDestination:
    """Build the logical VDE view target for a model."""

    return _build_virtual_destination(
        adapter=adapter,
        target=target,
        virtual_environment_name=virtual_environment_name,
        unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
    )
