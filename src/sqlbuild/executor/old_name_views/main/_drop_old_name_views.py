"""Drop expired or requested compatibility views and record the drops."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.executor.janitor.models import JanitorOldNameView, JanitorOldNameViewPlanning
from sqlbuild.executor.old_name_views._helpers.janitor import apply_old_name_view_drops


def drop_old_name_views(
    *,
    plan: JanitorOldNameViewPlanning,
    adapter: BaseAdapter,
    connection: Any,
    recorder: StatementRecorder,
    run_id: str,
) -> tuple[JanitorOldNameView, ...]:
    """Drop planned views, then append a drop fact for each dropped or vanished view."""

    return apply_old_name_view_drops(
        plan=plan, adapter=adapter, connection=connection, recorder=recorder, run_id=run_id
    )
