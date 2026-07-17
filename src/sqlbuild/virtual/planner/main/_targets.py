"""Public virtual target helpers."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.virtual.planner._helpers.targets import build_destination_from_physical_relation
from sqlbuild.virtual.state.models import PhysicalRelationRecord


def build_virtual_destination_from_physical_relation(
    *,
    adapter: BaseAdapter,
    relation: PhysicalRelationRecord,
    fallback_target: CompiledRelationLocation,
) -> CompiledRelationLocation:
    """Build a compiled relation location from a tracked physical relation."""

    return build_destination_from_physical_relation(
        adapter=adapter,
        relation=relation,
        fallback_target=fallback_target,
    )
