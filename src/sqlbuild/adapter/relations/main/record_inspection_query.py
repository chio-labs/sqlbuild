"""Record one planner warehouse inspection read."""

from __future__ import annotations

from sqlbuild.adapter.relations._helpers.inspection_context import emit_inspection_record
from sqlbuild.adapter.relations.models import InspectionQueryRecord


def record_inspection_query(*, record: InspectionQueryRecord) -> None:
    """Log one inspection read and forward it to the active verbose sink."""

    return emit_inspection_record(record=record)
