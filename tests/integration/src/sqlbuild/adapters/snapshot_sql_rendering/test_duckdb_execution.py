"""Cross-adapter snapshot SQL executed on DuckDB; see helpers for the adapter shims."""

from __future__ import annotations

import pytest

from tests.integration.src.sqlbuild.adapters.snapshot_sql_rendering._test_types import (
    SnapshotExecutionTestCase,
)
from tests.integration.src.sqlbuild.adapters.snapshot_sql_rendering.helpers import (
    CURRENT_CHECK_HARD_DELETES,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP_HARD_DELETES,
    FIRST_CLOCK_DAY,
    HISTORICAL_CHECK,
    HISTORICAL_CHECK_HARD_DELETES,
    HISTORICAL_TIMESTAMP,
    HISTORICAL_TIMESTAMP_HARD_DELETES,
    SnapshotExecutionRun,
    SnapshotExecutionScenario,
    build_execution_runs,
    run_snapshot_builds,
)

_CHECK_DELETE_AND_REAPPEAR_ROWS: tuple[tuple[object, ...], ...] = (
    (1, "active", 1),
    (2, "active", 1),
    (1, "active", 2),
    (1, "active", 3),
    (2, "active", 3),
)
_TIMESTAMP_DELETE_AND_REAPPEAR_ROWS: tuple[tuple[object, ...], ...] = (
    (1, "basic", 1, 1),
    (2, "pro", 1, 1),
    (1, "basic", 1, 2),
    (1, "basic", 1, 3),
    (2, "pro", 1, 3),
)

_HISTORICAL_SCENARIOS: tuple[SnapshotExecutionScenario, ...] = (
    SnapshotExecutionScenario(
        description="check without hard deletes records changes and ignores missing keys",
        kind=HISTORICAL_CHECK,
        builds=(
            ((1, "active", 1), (2, "active", 1)),
            ((1, "active", 1), (2, "active", 1), (1, "paused", 2), (1, "paused", 3)),
        ),
        expected_history=((1, "active", 1, 2), (1, "paused", 2, None), (2, "active", 1, None)),
    ),
    SnapshotExecutionScenario(
        description="check initial observation",
        kind=HISTORICAL_CHECK_HARD_DELETES,
        builds=(((1, "active", 1), (2, "active", 1)),),
        expected_history=((1, "active", 1, None), (2, "active", 1, None)),
    ),
    SnapshotExecutionScenario(
        description="check hard delete",
        kind=HISTORICAL_CHECK_HARD_DELETES,
        builds=(_CHECK_DELETE_AND_REAPPEAR_ROWS[:2], _CHECK_DELETE_AND_REAPPEAR_ROWS[:3]),
        expected_history=((1, "active", 1, None), (2, "active", 1, 2)),
    ),
    SnapshotExecutionScenario(
        description="check unchanged reappearance across builds",
        kind=HISTORICAL_CHECK_HARD_DELETES,
        builds=(
            _CHECK_DELETE_AND_REAPPEAR_ROWS[:2],
            _CHECK_DELETE_AND_REAPPEAR_ROWS[:3],
            _CHECK_DELETE_AND_REAPPEAR_ROWS,
        ),
        expected_history=(
            (1, "active", 1, None),
            (2, "active", 1, 2),
            (2, "active", 3, None),
        ),
    ),
    SnapshotExecutionScenario(
        description="check unchanged reappearance in the same build",
        kind=HISTORICAL_CHECK_HARD_DELETES,
        builds=(_CHECK_DELETE_AND_REAPPEAR_ROWS[:2], _CHECK_DELETE_AND_REAPPEAR_ROWS),
        expected_history=(
            (1, "active", 1, None),
            (2, "active", 1, 2),
            (2, "active", 3, None),
        ),
    ),
    SnapshotExecutionScenario(
        description="timestamp without hard deletes records updated_at changes",
        kind=HISTORICAL_TIMESTAMP,
        builds=(
            ((1, "basic", 1, 1),),
            ((1, "basic", 1, 1), (1, "pro", 2, 3), (1, "pro", 2, 4)),
        ),
        expected_history=((1, "basic", 1, 2), (1, "pro", 2, None)),
    ),
    SnapshotExecutionScenario(
        description="timestamp initial observation",
        kind=HISTORICAL_TIMESTAMP_HARD_DELETES,
        builds=(_TIMESTAMP_DELETE_AND_REAPPEAR_ROWS[:2],),
        expected_history=((1, "basic", 1, None), (2, "pro", 1, None)),
    ),
    SnapshotExecutionScenario(
        description="timestamp hard delete",
        kind=HISTORICAL_TIMESTAMP_HARD_DELETES,
        builds=(
            _TIMESTAMP_DELETE_AND_REAPPEAR_ROWS[:2],
            _TIMESTAMP_DELETE_AND_REAPPEAR_ROWS[:3],
        ),
        expected_history=((1, "basic", 1, None), (2, "pro", 1, 2)),
    ),
    SnapshotExecutionScenario(
        description="timestamp change followed by an unchanged repeat in one build",
        kind=HISTORICAL_TIMESTAMP_HARD_DELETES,
        builds=(
            ((1, "basic", 1, 1),),
            ((1, "basic", 1, 1), (1, "pro", 2, 3), (1, "pro", 2, 4)),
        ),
        expected_history=((1, "basic", 1, 2), (1, "pro", 2, None)),
    ),
    SnapshotExecutionScenario(
        description="check change followed by an unchanged repeat in one build",
        kind=HISTORICAL_CHECK_HARD_DELETES,
        builds=(
            ((1, "active", 1),),
            ((1, "active", 1), (1, "paused", 2), (1, "paused", 3)),
        ),
        expected_history=((1, "active", 1, 2), (1, "paused", 2, None)),
    ),
    SnapshotExecutionScenario(
        description="check multiple delete and reappear cycles in one build",
        kind=HISTORICAL_CHECK_HARD_DELETES,
        builds=(
            _CHECK_DELETE_AND_REAPPEAR_ROWS[:2],
            (
                *_CHECK_DELETE_AND_REAPPEAR_ROWS,
                (1, "active", 4),
                (1, "active", 5),
                (2, "active", 5),
            ),
        ),
        expected_history=(
            (1, "active", 1, None),
            (2, "active", 1, 2),
            (2, "active", 3, 4),
            (2, "active", 5, None),
        ),
    ),
    SnapshotExecutionScenario(
        description="check reappearance, change and change back in one build",
        kind=HISTORICAL_CHECK_HARD_DELETES,
        builds=(
            _CHECK_DELETE_AND_REAPPEAR_ROWS[:2],
            (
                *_CHECK_DELETE_AND_REAPPEAR_ROWS,
                (1, "active", 4),
                (2, "paused", 4),
                (1, "active", 5),
                (2, "active", 5),
            ),
        ),
        expected_history=(
            (1, "active", 1, None),
            (2, "active", 1, 2),
            (2, "active", 3, 4),
            (2, "paused", 4, 5),
            (2, "active", 5, None),
        ),
    ),
    SnapshotExecutionScenario(
        description="timestamp unchanged updated_at reappearance across builds",
        kind=HISTORICAL_TIMESTAMP_HARD_DELETES,
        builds=(
            _TIMESTAMP_DELETE_AND_REAPPEAR_ROWS[:2],
            _TIMESTAMP_DELETE_AND_REAPPEAR_ROWS[:3],
            _TIMESTAMP_DELETE_AND_REAPPEAR_ROWS,
        ),
        expected_history=((1, "basic", 1, None), (2, "pro", 1, 2), (2, "pro", 3, None)),
    ),
    SnapshotExecutionScenario(
        description="timestamp unchanged updated_at reappearance in the same build",
        kind=HISTORICAL_TIMESTAMP_HARD_DELETES,
        builds=(_TIMESTAMP_DELETE_AND_REAPPEAR_ROWS[:2], _TIMESTAMP_DELETE_AND_REAPPEAR_ROWS),
        expected_history=((1, "basic", 1, None), (2, "pro", 1, 2), (2, "pro", 3, None)),
    ),
    SnapshotExecutionScenario(
        description="timestamp multiple delete and reappear cycles in one build",
        kind=HISTORICAL_TIMESTAMP_HARD_DELETES,
        builds=(
            _TIMESTAMP_DELETE_AND_REAPPEAR_ROWS[:2],
            (
                *_TIMESTAMP_DELETE_AND_REAPPEAR_ROWS,
                (1, "basic", 1, 4),
                (1, "basic", 1, 5),
                (2, "pro", 1, 5),
            ),
        ),
        expected_history=(
            (1, "basic", 1, None),
            (2, "pro", 1, 2),
            (2, "pro", 3, 4),
            (2, "pro", 5, None),
        ),
    ),
    SnapshotExecutionScenario(
        description="timestamp changed reappearance starts at the new updated_at",
        kind=HISTORICAL_TIMESTAMP_HARD_DELETES,
        builds=(
            _TIMESTAMP_DELETE_AND_REAPPEAR_ROWS[:2],
            _TIMESTAMP_DELETE_AND_REAPPEAR_ROWS[:3],
            (*_TIMESTAMP_DELETE_AND_REAPPEAR_ROWS[:3], (1, "basic", 1, 4), (2, "team", 3, 4)),
            (*_TIMESTAMP_DELETE_AND_REAPPEAR_ROWS[:3], (1, "basic", 1, 4), (2, "team", 3, 4)),
        ),
        expected_history=((1, "basic", 1, None), (2, "pro", 1, 2), (2, "team", 3, None)),
    ),
)

_WINDOWED_SOURCE_SCENARIOS: tuple[SnapshotExecutionScenario, ...] = (
    SnapshotExecutionScenario(
        description="check reappearance after the deletion observation left the source window",
        kind=HISTORICAL_CHECK_HARD_DELETES,
        builds=(
            _CHECK_DELETE_AND_REAPPEAR_ROWS[:2],
            _CHECK_DELETE_AND_REAPPEAR_ROWS[:3],
            _CHECK_DELETE_AND_REAPPEAR_ROWS[3:],
        ),
        expected_history=(
            (1, "active", 1, None),
            (2, "active", 1, 2),
            (2, "active", 3, None),
        ),
    ),
    SnapshotExecutionScenario(
        description="timestamp reappearance after the deletion observation left the source window",
        kind=HISTORICAL_TIMESTAMP_HARD_DELETES,
        builds=(
            _TIMESTAMP_DELETE_AND_REAPPEAR_ROWS[:2],
            _TIMESTAMP_DELETE_AND_REAPPEAR_ROWS[:3],
            _TIMESTAMP_DELETE_AND_REAPPEAR_ROWS[3:],
        ),
        expected_history=((1, "basic", 1, None), (2, "pro", 1, 2), (2, "pro", 3, None)),
    ),
)

_CURRENT_STATE_SCENARIOS: tuple[SnapshotExecutionScenario, ...] = (
    SnapshotExecutionScenario(
        description="current timestamp reappearance updated_at equals deletion time",
        kind=CURRENT_TIMESTAMP_HARD_DELETES,
        builds=(
            ((1, "basic", 1), (2, "pro", 1)),
            ((1, "basic", 1),),
            ((1, "basic", 1), (2, "team", FIRST_CLOCK_DAY + 1)),
            ((1, "basic", 1), (2, "team", FIRST_CLOCK_DAY + 1)),
        ),
        expected_history=(
            (1, "basic", 1, None),
            (2, "pro", 1, FIRST_CLOCK_DAY + 1),
            (2, "team", FIRST_CLOCK_DAY + 2, None),
        ),
    ),
    SnapshotExecutionScenario(
        description="current timestamp without hard deletes records updated_at changes",
        kind=CURRENT_TIMESTAMP,
        builds=(((1, "basic", 1),), ((1, "pro", 5),)),
        expected_history=((1, "basic", 1, 5), (1, "pro", 5, None)),
    ),
    SnapshotExecutionScenario(
        description="current timestamp hard deletes keep updated_at for changes",
        kind=CURRENT_TIMESTAMP_HARD_DELETES,
        builds=(((1, "basic", 1),), ((1, "pro", 5),)),
        expected_history=((1, "basic", 1, 5), (1, "pro", 5, None)),
    ),
    SnapshotExecutionScenario(
        description="current check hard delete then unchanged reappearance",
        kind=CURRENT_CHECK_HARD_DELETES,
        builds=(((1, "active"), (2, "active")), ((1, "active"),), ((1, "active"), (2, "active"))),
        expected_history=(
            (1, "active", FIRST_CLOCK_DAY, None),
            (2, "active", FIRST_CLOCK_DAY, FIRST_CLOCK_DAY + 1),
            (2, "active", FIRST_CLOCK_DAY + 2, None),
        ),
    ),
    SnapshotExecutionScenario(
        description="current timestamp hard delete then unchanged reappearance",
        kind=CURRENT_TIMESTAMP_HARD_DELETES,
        builds=(
            ((1, "basic", 1), (2, "pro", 1)),
            ((1, "basic", 1),),
            ((1, "basic", 1), (2, "pro", 1)),
        ),
        expected_history=(
            (1, "basic", 1, None),
            (2, "pro", 1, FIRST_CLOCK_DAY + 1),
            (2, "pro", FIRST_CLOCK_DAY + 2, None),
        ),
    ),
    SnapshotExecutionScenario(
        description="current timestamp hard delete then reappearance with a newer updated_at",
        kind=CURRENT_TIMESTAMP_HARD_DELETES,
        builds=(
            ((1, "basic", 1), (2, "pro", 1)),
            ((1, "basic", 1),),
            ((1, "basic", 1), (2, "team", 5)),
        ),
        expected_history=(
            (1, "basic", 1, None),
            (2, "pro", 1, FIRST_CLOCK_DAY + 1),
            (2, "team", FIRST_CLOCK_DAY + 2, None),
        ),
    ),
)

_RUNS: tuple[SnapshotExecutionRun, ...] = build_execution_runs(
    incremental_scenarios=(
        *_HISTORICAL_SCENARIOS,
        *_WINDOWED_SOURCE_SCENARIOS,
        *_CURRENT_STATE_SCENARIOS,
    ),
    full_history_scenarios=_HISTORICAL_SCENARIOS,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotExecutionTestCase(
            description=f"{run.adapter.name}: {run.scenario.description} ({run.path})",
            adapter_type=run.adapter.adapter_type,
            normalize_sql=run.adapter.normalize_sql,
            source_select_sql=run.scenario.kind.source_select_sql,
            render_initial=run.scenario.kind.render_initial,
            render_apply=run.scenario.kind.render_apply,
            history_sql=run.scenario.kind.history_sql,
            builds=run.builds,
            expected_history=run.scenario.expected_history,
        )
        for run in _RUNS
    ],
    ids=lambda case: case.description,
)
def test_given_snapshot_scenario_when_executing_adapter_sql_on_duckdb_then_history_matches(
    test_case: SnapshotExecutionTestCase,
) -> None:
    history: tuple[tuple[object, ...], ...]
    violations: tuple[object, ...] | None
    history, violations = run_snapshot_builds(test_case)

    assert history == test_case.expected_history
    assert violations == (0, 0, 0)


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotExecutionTestCase(
            description=f"{run.adapter.name}: {run.scenario.description} interrupted",
            adapter_type=run.adapter.adapter_type,
            normalize_sql=run.adapter.normalize_sql,
            source_select_sql=run.scenario.kind.source_select_sql,
            render_initial=run.scenario.kind.render_initial,
            render_apply=run.scenario.kind.render_apply,
            history_sql=run.scenario.kind.history_sql,
            builds=run.builds,
            expected_history=run.scenario.expected_history,
            retry_after_insert=True,
        )
        for run in _RUNS
        if run.scenario.kind is CURRENT_TIMESTAMP_HARD_DELETES
    ],
    ids=lambda case: case.description,
)
def test_given_interrupted_timestamp_insert_when_retrying_then_history_is_idempotent(
    test_case: SnapshotExecutionTestCase,
) -> None:
    history, violations = run_snapshot_builds(test_case)

    assert history == test_case.expected_history
    assert violations == (0, 0, 0)
