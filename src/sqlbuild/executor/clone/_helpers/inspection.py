"""Clone relation inspection phase."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import RelationLookup
from sqlbuild.adapter.relations.main.relation_lookup import build_relation_lookup
from sqlbuild.compiler.planner.models import CloneSourcePlanEntry, ModelPlanEntry, SeedPlanEntry
from sqlbuild.executor.clone.models import CloneExecutionInput
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle


def build_clone_relation_lookup(
    *,
    inputs: CloneExecutionInput,
    clonable_entries: tuple[
        tuple[
            CloneSourcePlanEntry | SeedPlanEntry | ModelPlanEntry,
            CloneSourcePlanEntry | SeedPlanEntry | ModelPlanEntry,
        ],
        ...,
    ],
) -> RelationLookup:
    """Inspect clone origins and dependencies as one bounded operation."""

    with OperationLifecycle(
        operation_kind="clone", operation_name="clone_relation_inspection"
    ) as inspection:
        relation_lookup: RelationLookup = build_relation_lookup(
            adapter=inputs.adapter,
            connection=inputs.destination_connection,
            locations=tuple(
                (
                    origin_entry.destination.database,
                    origin_entry.destination.schema,
                    origin_entry.destination.name,
                )
                for _, origin_entry in clonable_entries
            )
            + tuple(
                (location.database, location.schema, location.name)
                for location in inputs.dependency_locations.values()
            ),
        )
        inspection.completed(metadata={"item_count": len(clonable_entries)})
        return relation_lookup
