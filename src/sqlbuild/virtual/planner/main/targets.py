"""Public virtual target helpers."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledRelationTarget
from sqlbuild.virtual.planner.helpers.targets import build_target_from_physical_relation
from sqlbuild.virtual.state.models import PhysicalRelationRecord


def build_virtual_target_from_physical_relation(
    *,
    adapter: BaseAdapter,
    relation: PhysicalRelationRecord,
    fallback_target: CompiledRelationTarget,
) -> CompiledRelationTarget:
    """Build a compiled target from a tracked physical relation."""

    return build_target_from_physical_relation(
        adapter=adapter,
        relation=relation,
        fallback_target=fallback_target,
    )
