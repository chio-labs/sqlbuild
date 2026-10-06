"""Public destination and staging identifier resolution for table models."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.executor.run._helpers.execution.table_targets import (
    resolve_table_targets as _resolve_table_targets,
)
from sqlbuild.executor.run.models import TableTargets


def resolve_table_targets(*, adapter: BaseAdapter, entry: ModelPlanEntry) -> TableTargets:
    """Resolve destination and staging identifiers for one table model."""

    return _resolve_table_targets(adapter=adapter, entry=entry)
