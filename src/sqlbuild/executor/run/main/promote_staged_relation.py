"""Public staged-relation promotion shared by build-aside rebuilds and model migrations."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.executor.run._helpers.materializations.full_refresh import (
    promote_staged_relation as _promote_staged_relation,
)


def promote_staged_relation(
    *,
    adapter: BaseAdapter,
    connection: Any,
    target_qualified: str,
    staged_qualified: str,
    displaced_qualified: str,
    target_exists: bool,
    statement_recorder: StatementRecorder,
) -> None:
    """Promote a staged relation into its target, moving a live target to the displaced name."""

    _ = _promote_staged_relation(
        adapter=adapter,
        connection=connection,
        target_qualified=target_qualified,
        staged_qualified=staged_qualified,
        displaced_qualified=displaced_qualified,
        target_exists=target_exists,
        statement_recorder=statement_recorder,
    )
