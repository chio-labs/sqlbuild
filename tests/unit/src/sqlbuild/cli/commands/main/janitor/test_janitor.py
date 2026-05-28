"""Tests for janitor command behavior."""

from __future__ import annotations

import builtins

import pytest

from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.cli.commands.main.janitor import _confirm
from sqlbuild.executor.janitor.models import (
    JanitorDeleteCandidate,
    JanitorPlan,
    JanitorRelationKey,
)
from tests.unit.src.sqlbuild.cli.commands.main.janitor._test_types import (
    JanitorConfirmationInterruptTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorConfirmationInterruptTestCase(
            description="treats keyboard interrupt at confirmation as cancellation",
            expected_result=False,
            expected_output_fragments=(
                "Janitor will delete 1 objects from dev.",
                "Type `delete 1 objects from dev` to continue: ",
            ),
            unexpected_output_fragments=("KeyboardInterrupt", "Traceback"),
        )
    ],
    ids=["treats keyboard interrupt at confirmation as cancellation"],
)
def test_given_janitor_confirmation_when_keyboard_interrupt_then_returns_cancelled(
    test_case: JanitorConfirmationInterruptTestCase,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan: JanitorPlan = JanitorPlan(
        environment_name="dev",
        retention_days=30,
        candidates=(
            JanitorDeleteCandidate(
                key=JanitorRelationKey(database=None, schema="dev", name="stale_model"),
                relation=RelationInfo(
                    database=None,
                    schema="dev",
                    name="stale_model",
                    relation_type="table",
                ),
                age_timestamp=None,
            ),
        ),
    )

    def interrupting_input() -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(builtins, "input", interrupting_input)

    result: bool = _confirm(plan=plan)

    output: str = capsys.readouterr().out
    assert result is test_case.expected_result
    for fragment in test_case.expected_output_fragments:
        assert fragment in output
    for fragment in test_case.unexpected_output_fragments:
        assert fragment not in output
