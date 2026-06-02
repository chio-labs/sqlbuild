"""Tests for janitor command behavior."""

from __future__ import annotations

import builtins
from io import StringIO

import pytest

from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.cli.commands.main.helpers.janitor.output import write_disabled, write_plan
from sqlbuild.cli.commands.main.janitor import _confirm
from sqlbuild.executor.janitor.models import (
    JanitorDeleteCandidate,
    JanitorPlan,
    JanitorRelationKey,
)
from tests.unit.src.sqlbuild.cli.commands.main.janitor._test_types import (
    JanitorConfirmationInterruptTestCase,
    JanitorDisabledOutputTestCase,
    JanitorPlanOutputTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.janitor.helpers import build_janitor_plan


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
        target_name="dev",
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


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorDisabledOutputTestCase(
            description="preserves disabled no-color output",
            use_color=False,
            expected_output="Janitor is disabled for this project.\n\n"
            "Janitor is opt-in. It previews stale warehouse objects and asks before "
            "deleting anything.\n\n"
            "Add this block to sqlbuild_project.toml:\n\n"
            "janitor:\n"
            "  enabled: true\n"
            "  retention_days: 30\n\n"
            "After enabling, run janitor again to preview cleanup:\n"
            "  sqb janitor\n",
        )
    ],
    ids=["preserves disabled no-color output"],
)
def test_given_disabled_janitor_when_writing_without_color_then_preserves_output(
    test_case: JanitorDisabledOutputTestCase,
) -> None:
    stream: StringIO = StringIO()

    write_disabled(stream=stream, use_color=test_case.use_color)

    assert stream.getvalue() == test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorDisabledOutputTestCase(
            description="styles disabled title",
            use_color=True,
            expected_prefix="\033[33m\033[1mJanitor is disabled for this project.\033[0m",
        )
    ],
    ids=["styles disabled title"],
)
def test_given_disabled_janitor_when_writing_with_color_then_styles_title(
    test_case: JanitorDisabledOutputTestCase,
) -> None:
    stream: StringIO = StringIO()

    write_disabled(stream=stream, use_color=test_case.use_color)

    assert test_case.expected_prefix is not None
    assert stream.getvalue().startswith(test_case.expected_prefix)
    assert (
        "\033[33mJanitor is opt-in. It previews stale warehouse objects and asks before "
        "deleting anything.\033[0m"
    ) in stream.getvalue()
    assert "\033[34msqb janitor\033[0m" in stream.getvalue()


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorPlanOutputTestCase(
            description="preserves no-color plan fragments",
            use_color=False,
            expected_output_fragments=(
                "Janitor preview  dev",
                "  retention              30 days",
                "  eligible for deletion  1",
                "Skipped schemas\n  dev  contains active source raw.orders",
                "Eligible objects\n  dev.stale_model",
                "Eligible checkpoints\n  cp_1  dev",
                "Eligible detached VDEs\n  branch_old  detached virtual environment",
                "Eligible expired VDEs\n  branch_expired  expired virtual environment",
                "Eligible state backups\n  backup_1  sqlbuild_state",
                "Eligible expired locks\n  lock_1  worker_1",
                "Skipped objects\n  dev.source_table  source relation",
            ),
            unexpected_output_fragments=("\033[",),
        )
    ],
    ids=["preserves no-color plan fragments"],
)
def test_given_janitor_plan_when_writing_without_color_then_preserves_output_fragments(
    test_case: JanitorPlanOutputTestCase,
) -> None:
    plan: JanitorPlan = build_janitor_plan()
    stream: StringIO = StringIO()

    write_plan(plan=plan, stream=stream, use_color=test_case.use_color)

    output: str = stream.getvalue()
    for fragment in test_case.expected_output_fragments:
        assert fragment in output
    for fragment in test_case.unexpected_output_fragments:
        assert fragment not in output


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorPlanOutputTestCase(
            description="uses semantic plan colors",
            use_color=True,
            expected_output_fragments=(
                "\033[32m\033[1mJanitor preview\033[0m",
                "\033[34m\033[1mdev\033[0m",
                "\033[34m30 days\033[0m",
                "eligible for deletion  \033[33m1\033[0m",
                "\033[32mEligible objects\033[0m",
                "\033[34m\033[1mdev.stale_model\033[0m",
                "\033[2msource relation\033[0m",
            ),
        )
    ],
    ids=["uses semantic plan colors"],
)
def test_given_janitor_plan_when_writing_with_color_then_uses_semantic_colors(
    test_case: JanitorPlanOutputTestCase,
) -> None:
    plan: JanitorPlan = build_janitor_plan()
    stream: StringIO = StringIO()

    write_plan(plan=plan, stream=stream, use_color=test_case.use_color)

    output: str = stream.getvalue()
    for fragment in test_case.expected_output_fragments:
        assert fragment in output
