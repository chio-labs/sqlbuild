"""A finished session outcome as Python's analysis, for hand-built model inputs only."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.analysis_session._helpers.session_rows import outcome_analysis
from sqlbuild.compiler.analysis_session.types import ContractRow, OutcomeRow
from sqlbuild.compiler.compile.models import ModelSqlAnalysis


def session_outcome_analysis(
    *, session: Any, position: int, placeholders: dict[str, str] | None
) -> ModelSqlAnalysis:
    """The outcome at `position` of a finished session as an explicit boundary conversion."""

    outcome: OutcomeRow
    contract: ContractRow
    outcome, contract = session.outcome_rows(position)
    return outcome_analysis(outcome=outcome, contract=contract[1], placeholders=placeholders)
