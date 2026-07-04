from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.cli.commands.main.commands import dbt_clone as dbt_clone_module
from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from sqlbuild.integrations.dbt.models import DbtCloneRun
from tests.unit.src.sqlbuild.cli.commands.main.dbt._test_types import (
    DbtCloneCommandOutputTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtCloneCommandOutputTestCase(
            description="renders shared clone header progress rows and summary",
            expected_stderr_fragments=(
                "Connected to snowflake. (0.01s)",
                "Applied clone plan. (0.02s)",
            ),
            expected_stdout_fragments=(
                "sqb clone  origin=master destination=dev  (1 relation)",
                "1/1  cloned",
                "RACING.STAGING.RACE__STG_HORSE -> RACING.DEV.RACE__STG_HORSE  OK  0.92s",
                "Completed successfully.",
                "CLONED=1",
                "TOTAL=1",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_dbt_clone_when_streaming_then_renders_native_clone_output_shape(
    test_case: DbtCloneCommandOutputTestCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def run_dbt_clone_from_project(
        *,
        project_dir: Path,
        args: tuple[str, ...],
        on_progress: Callable[[str], None],
        on_clone_start: Callable[[str, str, int], None],
        on_item: Callable[[int, int, CloneItemResult], None],
    ) -> DbtCloneRun:
        del project_dir, args
        on_progress("Connecting to snowflake...")
        on_progress("Connected to snowflake. (0.01s)")
        on_progress("Applying clone plan...")
        on_clone_start("master", "dev", 1)
        item: CloneItemResult = CloneItemResult(
            name="race__stg_horse",
            action=CloneAction.CLONED,
            status=CloneStatus.SUCCESS,
            origin_relation="RACING.STAGING.RACE__STG_HORSE",
            destination_relation="RACING.DEV.RACE__STG_HORSE",
            duration_seconds=0.92,
        )
        on_item(1, 1, item)
        on_progress("Applied clone plan. (0.02s)")
        return DbtCloneRun(
            result=CloneExecutionResult(item_results=(item,)),
            origin_label="master",
            destination_label="dev",
        )

    monkeypatch.setattr(
        dbt_clone_module,
        "run_dbt_clone_from_project",
        run_dbt_clone_from_project,
    )
    monkeypatch.setattr(dbt_clone_module, "supports_color", lambda: False)

    exit_code: int = dbt_clone_module.run_dbt_clone_command(
        project_dir=Path("/project"),
        args=("--select", "tag:unicron"),
        no_color=True,
    )

    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == 0
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in captured.err
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in captured.out
