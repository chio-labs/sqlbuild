"""Planned project relations for hard-coded relation name guards."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.pipeline._helpers.relation_targets import (
    build_project_relation_targets_impl,
)
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.python_nodes.models import SqlResourceRef


def build_project_relation_targets(
    *, adapter: BaseAdapter, plan_output: PlanOutput
) -> dict[SqlResourceRef, str] | None:
    """Return every planned project relation for hard-coded name warnings, or None when off."""

    return build_project_relation_targets_impl(adapter=adapter, plan_output=plan_output)
