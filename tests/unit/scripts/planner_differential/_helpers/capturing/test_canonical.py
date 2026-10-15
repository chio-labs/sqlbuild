"""Canonicalisation masks only run-specific values so two runs of one tree compare equal."""

from __future__ import annotations

import pytest

from scripts.planner_differential._helpers.capturing.canonical import (
    canonical_plan_capture,
    canonical_value,
    mask_console_text,
    mask_text,
)
from scripts.planner_differential._helpers.capturing.state_tables import state_delta
from sqlbuild._native import render_stage_capture
from tests.unit.scripts.planner_differential._helpers.capturing._test_types import (
    CanonicalValueTestCase,
    MaskTextTestCase,
    PlanCaptureTestCase,
    StateDeltaTestCase,
)
from tests.unit.scripts.planner_differential._helpers.capturing.helpers import (
    TEST_MASKS,
    expected_order_entry,
    order_plan,
)


@pytest.mark.parametrize(
    "test_case",
    [
        MaskTextTestCase(
            description="run_id",
            raw="run 20261014T002537Z_7e9b74a9fefc",
            expected_text="run <invocation-id>",
        ),
        MaskTextTestCase(
            description="project_path_before_work_path",
            raw="/runs/work/orders/project/models/a.sql and /runs/work/other",
            expected_text="<project>/models/a.sql and <work>/other",
        ),
        MaskTextTestCase(
            description="timestamp_on_the_run_date",
            raw="built at 2026-10-14T09:30:00.123+00:00",
            expected_text="built at <recent-timestamp>",
        ),
        MaskTextTestCase(
            description="retention_expiry_after_the_run_date",
            raw="expires 2026-11-13 00:38:45.472672",
            expected_text="expires <recent-timestamp>",
        ),
        MaskTextTestCase(
            description="data_timestamp_is_kept",
            raw="cursor 2026-04-02 12:00:00 to 2026-04-05 14:30:00",
            expected_text="cursor 2026-04-02 12:00:00 to 2026-04-05 14:30:00",
        ),
        MaskTextTestCase(
            description="compact_archive_timestamp",
            raw="_sqb_archive__20261014t004426z__migration_origin__orders",
            expected_text="_sqb_archive__<recent-timestamp>__migration_origin__orders",
        ),
        MaskTextTestCase(
            description="replay_range_date_relative_to_the_run_date",
            raw="range 2026-10-11 → 2026-10-14",
            expected_text="range <run-date-3d> → <run-date+0d>",
        ),
        MaskTextTestCase(
            description="retention_date_relative_to_the_run_date",
            raw="live until 2026-11-13",
            expected_text="live until <run-date+30d>",
        ),
        MaskTextTestCase(
            description="fixed_data_date_is_kept",
            raw="partition 2026-04-02",
            expected_text="partition 2026-04-02",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_output_text_when_masking_then_only_run_specific_values_change(
    test_case: MaskTextTestCase,
) -> None:
    assert mask_text(text=test_case.raw, masks=TEST_MASKS) == test_case.expected_text


@pytest.mark.parametrize(
    "test_case",
    [
        MaskTextTestCase(
            description="elapsed_time",
            raw="Generated plan. (0.04s)",
            expected_text="Generated plan. (<elapsed>)",
        ),
        MaskTextTestCase(
            description="project_path_in_a_diagnostic",
            raw="error: /runs/work/orders/project/models/orders.sql:3:1",
            expected_text="error: <project>/models/orders.sql:3:1",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_console_text_when_masking_then_elapsed_times_are_masked(
    test_case: MaskTextTestCase,
) -> None:
    assert mask_console_text(text=test_case.raw, masks=TEST_MASKS) == test_case.expected_text


@pytest.mark.parametrize(
    "test_case",
    [
        CanonicalValueTestCase(
            description="volatile_keys",
            value={"run_id": "r1", "ts": "t", "migration_event_id": "e", "name": "orders"},
            expected_value={
                "run_id": "<volatile>",
                "ts": "<volatile>",
                "migration_event_id": "<volatile>",
                "name": "orders",
            },
        ),
        CanonicalValueTestCase(
            description="absent_volatile_value_stays_null",
            value={"completed_at": None},
            expected_value={"completed_at": None},
        ),
        CanonicalValueTestCase(
            description="non_string_key_mapping_is_sorted",
            value={"__mapping__": [[["model", "orders"], 2], [["loader", "customers"], 1]]},
            expected_value={
                "__mapping__": [[["loader", "customers"], 1], [["model", "orders"], 2]]
            },
        ),
        CanonicalValueTestCase(
            description="list_order_is_kept",
            value={"execution_order": ["orders", "customers"]},
            expected_value={"execution_order": ["orders", "customers"]},
        ),
        CanonicalValueTestCase(
            description="nested_strings_are_masked",
            value=[{"path": "/runs/work/orders/project/models/orders.sql"}],
            expected_value=[{"path": "<project>/models/orders.sql"}],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_decoded_json_when_canonicalising_then_volatile_values_are_masked(
    test_case: CanonicalValueTestCase,
) -> None:
    assert canonical_value(value=test_case.value, masks=TEST_MASKS) == test_case.expected_value


@pytest.mark.parametrize(
    "test_case",
    [
        StateDeltaTestCase(
            description="appended_rows_are_added",
            before={"db:main._sqlbuild_fingerprints": ['{"name": "orders"}']},
            after={"db:main._sqlbuild_fingerprints": ['{"name": "orders"}', '{"name": "orders"}']},
            expected_delta={
                "db:main._sqlbuild_fingerprints": {"added": [{"name": "orders"}], "removed": []}
            },
        ),
        StateDeltaTestCase(
            description="replaced_and_new_tables",
            before={"db:main._sqlbuild_migrations": ['{"state": "old"}']},
            after={
                "db:main._sqlbuild_migrations": ['{"state": "new"}'],
                "db:main._sqlbuild_old_name_views": ['{"view": "orders"}'],
            },
            expected_delta={
                "db:main._sqlbuild_migrations": {
                    "added": [{"state": "new"}],
                    "removed": [{"state": "old"}],
                },
                "db:main._sqlbuild_old_name_views": {
                    "added": [{"view": "orders"}],
                    "removed": [],
                },
            },
        ),
        StateDeltaTestCase(
            description="unchanged_tables_are_omitted",
            before={"db:main._sqlbuild_fingerprints": ['{"name": "orders"}']},
            after={"db:main._sqlbuild_fingerprints": ['{"name": "orders"}']},
            expected_delta={},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_state_rows_when_diffing_then_gained_and_lost_rows_are_reported(
    test_case: StateDeltaTestCase,
) -> None:
    assert state_delta(before=test_case.before, after=test_case.after) == test_case.expected_delta


@pytest.mark.parametrize(
    "test_case",
    [
        PlanCaptureTestCase(
            description="shared_entries_expanded_and_invocation_time_masked",
            value=order_plan(),
            expected_value={
                "__type__": (
                    "tests.unit.scripts.planner_differential._helpers.capturing.helpers:OrderPlan"
                ),
                "entries": [expected_order_entry(), expected_order_entry()],
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_plan_capture_document_when_canonicalising_then_nodes_expand_and_mask(
    test_case: PlanCaptureTestCase,
) -> None:
    assert (
        canonical_plan_capture(text=render_stage_capture(test_case.value), masks=TEST_MASKS)
        == test_case.expected_value
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
