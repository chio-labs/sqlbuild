"""Public clone fingerprint propagation entrypoint."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ModelPlanEntry, SeedPlanEntry
from sqlbuild.executor.clone.helpers.fingerprinting import copy_clone_fingerprints as _copy
from sqlbuild.executor.clone.models import CloneExecutionResult


def copy_clone_fingerprints(
    *,
    result: CloneExecutionResult,
    origin_model_entries: tuple[ModelPlanEntry, ...],
    destination_model_entries: tuple[ModelPlanEntry, ...],
    origin_seed_entries: tuple[SeedPlanEntry, ...],
    destination_seed_entries: tuple[SeedPlanEntry, ...],
    adapter: BaseAdapter,
    origin_connection: Any,
    destination_connection: Any,
    run_id: str,
    query_change_tracking: bool,
) -> None:
    _copy(
        result=result,
        origin_model_entries=origin_model_entries,
        destination_model_entries=destination_model_entries,
        origin_seed_entries=origin_seed_entries,
        destination_seed_entries=destination_seed_entries,
        adapter=adapter,
        origin_connection=origin_connection,
        destination_connection=destination_connection,
        run_id=run_id,
        query_change_tracking=query_change_tracking,
    )
