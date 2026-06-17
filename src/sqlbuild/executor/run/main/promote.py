"""Public relation promotion entrypoint for run execution."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.executor.run.helpers.promotion import promote_relation_to_destination


def promote_run_relation_to_destination(
    *,
    adapter: BaseAdapter,
    connection: Any,
    origin_relation: str,
    destination_relation: str,
    destination_database: str | None,
    destination_schema: str | None,
    destination_name: str,
    statement_recorder: StatementRecorder,
) -> None:
    """Promote an already-created run relation into its final destination."""

    promote_relation_to_destination(
        adapter=adapter,
        connection=connection,
        origin_relation=origin_relation,
        destination_relation=destination_relation,
        destination_database=destination_database,
        destination_schema=destination_schema,
        destination_name=destination_name,
        statement_recorder=statement_recorder,
    )
