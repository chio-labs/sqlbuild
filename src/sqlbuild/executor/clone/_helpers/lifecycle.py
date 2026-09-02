"""Clone destination preparation and finalization phases."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.compiler.planner.models import (
    CloneSourcePlanEntry,
    FunctionPlanEntry,
    ModelPlanEntry,
    SeedPlanEntry,
)
from sqlbuild.compiler.planner.types import RetentionPlanPhase
from sqlbuild.executor.clone._helpers.retention import apply_clone_namespace_retention_phase
from sqlbuild.executor.clone.models import (
    CloneExecutionInput,
    CloneExecutionResult,
    CloneItemResult,
)
from sqlbuild.executor.clone.types import CloneStatus
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle


def prepare_clone_destination(
    *,
    inputs: CloneExecutionInput,
    destination_entries: tuple[
        CloneSourcePlanEntry | SeedPlanEntry | ModelPlanEntry | FunctionPlanEntry, ...
    ],
) -> None:
    """Create destination schemas and apply namespace retention increases."""

    with OperationLifecycle(operation_kind="clone", operation_name="clone_namespace_preparation"):
        _ = _ensure_destination_schemas(
            destination_entries=destination_entries,
            adapter=inputs.adapter,
            destination_connection=inputs.destination_connection,
        )
    _ = apply_clone_namespace_retention_phase(
        requests=inputs.destination_retention_requests,
        adapter=inputs.adapter,
        connection=inputs.destination_connection,
        phase=RetentionPlanPhase.PRE,
    )


def finish_clone(
    *, results: list[CloneItemResult], inputs: CloneExecutionInput
) -> CloneExecutionResult:
    """Apply namespace decreases only after every clone item succeeds."""

    if results and all(result.status == CloneStatus.SUCCESS for result in results):
        _ = apply_clone_namespace_retention_phase(
            requests=inputs.destination_retention_requests,
            adapter=inputs.adapter,
            connection=inputs.destination_connection,
            phase=RetentionPlanPhase.POST,
        )
    return CloneExecutionResult(item_results=tuple(results))


def _ensure_destination_schemas(
    *,
    destination_entries: tuple[
        CloneSourcePlanEntry | SeedPlanEntry | ModelPlanEntry | FunctionPlanEntry, ...
    ],
    adapter: BaseAdapter,
    destination_connection: Any,
) -> None:
    schemas: set[tuple[str | None, str]] = set()
    entry: CloneSourcePlanEntry | SeedPlanEntry | ModelPlanEntry | FunctionPlanEntry
    for entry in destination_entries:
        if entry.destination.schema is not None:
            schemas.add((entry.destination.database, entry.destination.schema))
        if (
            isinstance(entry, FunctionPlanEntry)
            and entry.fingerprint_destination.schema is not None
        ):
            schemas.add(
                (entry.fingerprint_destination.database, entry.fingerprint_destination.schema)
            )
    recorder: StatementRecorder = StatementRecorder()
    for database, schema in sorted(schemas, key=lambda item: (item[0] or "", item[1])):
        _ = adapter.ensure_schema(
            connection=destination_connection,
            database=database,
            schema=schema,
            statement_recorder=recorder,
        )
