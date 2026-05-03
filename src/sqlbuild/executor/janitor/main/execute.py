"""Execute a janitor cleanup plan."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.executor.janitor.models import (
    JanitorDeleteCandidate,
    JanitorExecutionResult,
    JanitorPlan,
)


def execute_janitor_plan(
    *,
    plan: JanitorPlan,
    adapter: BaseAdapter,
    connection: Any,
) -> JanitorExecutionResult:
    """Delete all candidates in a janitor plan."""

    recorder: StatementRecorder = StatementRecorder()
    candidate: JanitorDeleteCandidate
    for candidate in plan.candidates:
        adapter.drop(
            connection,
            target=candidate.key.display_name(),
            if_exists=True,
            statement_recorder=recorder,
        )
    return JanitorExecutionResult(deleted=plan.candidates)
