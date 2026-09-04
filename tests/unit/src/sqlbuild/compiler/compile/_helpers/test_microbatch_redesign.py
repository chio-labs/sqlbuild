"""Behavior-focused coverage for the explicit microbatch cursor contract."""

import pytest

from sqlbuild.compiler.compile._helpers.config.model_validation import (
    validate_incremental_config,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileModelConfig
from sqlbuild.compiler.planner._helpers.resolve.cursor import (
    compute_cursor_bounds,
    resolve_effective_timestamp_grain,
)
from sqlbuild.compiler.planner._helpers.warehouse.snapshot import _watermark_type_is_compatible
from sqlbuild.compiler.planner.models import CursorBounds, CursorInputRelation, ModelCursorSnapshot
from sqlbuild.executor.run._helpers.validation.cursor_bounds import (
    resolve_effective_timestamp_grain as resolve_runtime_effective_timestamp_grain,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    AvailabilityStartFloorTestCase,
    MicrobatchCursorTypeTestCase,
    MicrobatchGrainOwnershipTestCase,
    MicrobatchRedesignBehaviorTestCase,
    WatermarkLimitValidationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        AvailabilityStartFloorTestCase(
            description="all mode intersects every capped producer lower edge",
            ranges=(
                ("2026-01-03", "2026-01-10"),
                ("2026-01-05", "2026-01-08"),
                (None, "2026-01-12"),
            ),
            mode="all",
            resolved_end="2026-01-08",
            expected_start="2026-01-05",
        ),
        AvailabilityStartFloorTestCase(
            description="any mode uses lower edge of producer supplying furthest end",
            ranges=(
                (None, "2026-01-08"),
                ("2026-01-05", "2026-01-12"),
            ),
            mode="any",
            resolved_end="2026-01-12",
            expected_start="2026-01-05",
        ),
        AvailabilityStartFloorTestCase(
            description="any mode remains unbounded when furthest producer is uncapped",
            ranges=(
                ("2026-01-05", "2026-01-08"),
                (None, "2026-01-12"),
            ),
            mode="any",
            resolved_end="2026-01-12",
            expected_start="2026-01-01",
        ),
        AvailabilityStartFloorTestCase(
            description="any tied end remains unbounded when one producer is uncapped",
            ranges=(
                ("2026-01-05", "2026-01-12"),
                (None, "2026-01-12"),
            ),
            mode="any",
            resolved_end="2026-01-12",
            expected_start="2026-01-01",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_producer_availability_ranges_when_clamping_bounds_then_mode_is_respected(
    test_case: AvailabilityStartFloorTestCase,
) -> None:
    assert (
        CursorBounds(start="2026-01-01", end=test_case.resolved_end)
        .clamp_to_availability(
            ranges=test_case.ranges,
            cursor_watermark_mode=test_case.mode,
            cursor_type="timestamp",
        )
        .start
        == test_case.expected_start
    )


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchGrainOwnershipTestCase(
            description="watermark consumer owns execution grain",
            consumer_grain="hour",
            producer_grain="month",
            microbatch_strategy="watermark",
            expected_grain="hour",
        ),
        MicrobatchGrainOwnershipTestCase(
            description="legacy cursor retains coarsest grain behavior",
            consumer_grain="hour",
            producer_grain="month",
            microbatch_strategy=None,
            expected_grain="month",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_consumer_and_producer_grains_when_resolving_then_strategy_owns_coarsening(
    test_case: MicrobatchGrainOwnershipTestCase,
) -> None:
    planner_grain: str | None = resolve_effective_timestamp_grain(
        cursor_type="timestamp",
        downstream_grain=test_case.consumer_grain,
        cursor_input_grains=(test_case.producer_grain,),
        microbatch_strategy=test_case.microbatch_strategy,
    )
    runtime_grain: str | None = resolve_runtime_effective_timestamp_grain(
        cursor_type="timestamp",
        downstream_grain=test_case.consumer_grain,
        cursor_input_relations=(
            CursorInputRelation(
                relation="main.producer",
                cursor_column="event_time",
                cursor_grain=test_case.producer_grain,
            ),
        ),
        microbatch_strategy=test_case.microbatch_strategy,
    )

    assert planner_grain == test_case.expected_grain
    assert runtime_grain == test_case.expected_grain


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchRedesignBehaviorTestCase(
            description="explicit watermark roles", expected_outcome=None
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_watermark_strategy_when_inputs_have_explicit_roles_then_config_is_valid(
    test_case: MicrobatchRedesignBehaviorTestCase,
) -> None:
    validate_incremental_config(
        config=CompileModelConfig(
            values={
                "materialized": "incremental",
                "incremental_strategy": "delete_insert",
                "incremental_mode": "microbatch",
                "microbatch_strategy": "watermark",
                "cursor_watermark_mode": "any",
                "cursor": "event_time",
                "cursor_type": "timestamp",
                "cursor_grain": "day",
                "cursor_start": "2026-01-01",
                "cursor_end": "2030-01-01",
                "cursor_inputs": {
                    "archive": {"column": "event_time", "roles": ["watermark"]},
                    "live": {"column": "event_time", "roles": ["filter", "watermark"]},
                },
                "batch_size": "1d",
                "lookback": "4d",
                "max_microbatches": 7,
            }
        ),
        model_name="events",
        ref_count=2,
        known_input_names=frozenset({"archive", "live"}),
    )
    assert test_case.expected_outcome is None


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchRedesignBehaviorTestCase(
            description="watermark declares latest batch cap", expected_outcome=None
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_watermark_strategy_when_nested_limit_caps_from_end_then_config_is_valid(
    test_case: MicrobatchRedesignBehaviorTestCase,
) -> None:
    validate_incremental_config(
        config=CompileModelConfig(
            values={
                "materialized": "incremental",
                "incremental_strategy": "delete_insert",
                "incremental_mode": "microbatch",
                "microbatch_strategy": "watermark",
                "cursor_watermark_mode": "all",
                "cursor": "event_time",
                "cursor_type": "timestamp",
                "cursor_grain": "day",
                "cursor_inputs": {
                    "events": {"column": "event_time", "roles": ["filter", "watermark"]}
                },
                "batch_size": "1d",
                "microbatch_limit": {"max_batches": 7, "action": "cap_from_end"},
            }
        ),
        model_name="events",
        ref_count=1,
        known_input_names=frozenset({"events"}),
    )
    assert test_case.expected_outcome is None


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchRedesignBehaviorTestCase(
            description="watermark shorthand rejected", expected_outcome="must use .*column .*roles"
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_watermark_strategy_when_cursor_inputs_use_shorthand_then_compilation_fails(
    test_case: MicrobatchRedesignBehaviorTestCase,
) -> None:
    with pytest.raises(CompileInputError, match=str(test_case.expected_outcome)):
        validate_incremental_config(
            config=CompileModelConfig(
                values={
                    "materialized": "incremental",
                    "incremental_strategy": "delete_insert",
                    "incremental_mode": "microbatch",
                    "microbatch_strategy": "watermark",
                    "cursor_watermark_mode": "all",
                    "cursor": "event_time",
                    "cursor_type": "timestamp",
                    "cursor_grain": "day",
                    "cursor_inputs": {"events": "event_time"},
                    "batch_size": "1d",
                }
            ),
            model_name="events",
            ref_count=1,
            known_input_names=frozenset({"events"}),
        )


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchRedesignBehaviorTestCase(
            description="watermark limit below lookback",
            expected_outcome="below the ordinary lookback requirement of 5 batches",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_model_limit_below_lookback_when_validating_then_compilation_fails(
    test_case: MicrobatchRedesignBehaviorTestCase,
) -> None:
    with pytest.raises(CompileInputError, match=str(test_case.expected_outcome)):
        validate_incremental_config(
            config=CompileModelConfig(
                values={
                    "materialized": "incremental",
                    "incremental_strategy": "delete_insert",
                    "incremental_mode": "microbatch",
                    "microbatch_strategy": "watermark",
                    "cursor_watermark_mode": "all",
                    "cursor": "event_time",
                    "cursor_type": "timestamp",
                    "cursor_grain": "day",
                    "cursor_inputs": {
                        "events": {
                            "column": "event_time",
                            "roles": ["filter", "watermark"],
                        }
                    },
                    "batch_size": "1d",
                    "lookback": "4d",
                    "max_microbatches": 4,
                }
            ),
            model_name="events",
            ref_count=1,
            known_input_names=frozenset({"events"}),
        )


@pytest.mark.parametrize(
    "test_case",
    (
        WatermarkLimitValidationTestCase(
            description="fixed lookback cap from start must leave one forward batch",
            incremental_strategy="delete_insert",
            batch_size="1d",
            lookback="1d",
            max_batches=2,
            action="cap_from_start",
            expected_error_fragment="ordinary lookback requirement of 3 batches",
        ),
        WatermarkLimitValidationTestCase(
            description="implicit idempotent lookback cap from start must leave one forward batch",
            incremental_strategy="delete_insert",
            batch_size="1d",
            lookback=None,
            max_batches=2,
            action="cap_from_start",
            expected_error_fragment="ordinary lookback requirement of 3 batches",
        ),
        WatermarkLimitValidationTestCase(
            description="calendar lookback cap from start must leave one forward batch",
            incremental_strategy="delete_insert",
            batch_size="1mo",
            lookback="1mo",
            max_batches=2,
            action="cap_from_start",
            expected_error_fragment="ordinary lookback requirement of 3 batches",
        ),
        WatermarkLimitValidationTestCase(
            description="effective batch cap from start resolves against cursor grain",
            incremental_strategy="delete_insert",
            batch_size="effective",
            lookback=None,
            max_batches=2,
            action="cap_from_start",
            expected_error_fragment="ordinary lookback requirement of 3 batches",
        ),
        WatermarkLimitValidationTestCase(
            description="mixed duration cap from start fails closed",
            incremental_strategy="delete_insert",
            batch_size="1d",
            lookback="1mo",
            max_batches=10,
            action="cap_from_start",
            expected_error_fragment="cannot prove forward progress",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_insufficient_capped_watermark_limit_when_validating_then_error_explains_progress(
    test_case: WatermarkLimitValidationTestCase,
) -> None:
    config: CompileModelConfig = CompileModelConfig(
        values={
            "materialized": "incremental",
            "incremental_strategy": test_case.incremental_strategy,
            "incremental_mode": "microbatch",
            "microbatch_strategy": "watermark",
            "cursor_watermark_mode": "all",
            "cursor": "event_time",
            "cursor_type": "timestamp",
            "cursor_grain": "day",
            "cursor_inputs": {
                "events": {
                    "column": "event_time",
                    "roles": ["filter", "watermark"],
                }
            },
            "batch_size": test_case.batch_size,
            "lookback": test_case.lookback,
            "microbatch_limit": {
                "max_batches": test_case.max_batches,
                "action": test_case.action,
            },
        }
    )

    assert test_case.expected_error_fragment is not None
    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        validate_incremental_config(
            config=config,
            model_name="events",
            ref_count=1,
            known_input_names=frozenset({"events"}),
        )


@pytest.mark.parametrize(
    "test_case",
    (
        WatermarkLimitValidationTestCase(
            description="cap from end may equal ordinary lookback requirement",
            incremental_strategy="delete_insert",
            batch_size="1d",
            lookback="1d",
            max_batches=2,
            action="cap_from_end",
            expected_error_fragment=None,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_sufficient_cap_from_end_limit_when_validating_then_config_is_accepted(
    test_case: WatermarkLimitValidationTestCase,
) -> None:
    assert test_case.expected_error_fragment is None
    validate_incremental_config(
        config=CompileModelConfig(
            values={
                "materialized": "incremental",
                "incremental_strategy": test_case.incremental_strategy,
                "incremental_mode": "microbatch",
                "microbatch_strategy": "watermark",
                "cursor_watermark_mode": "all",
                "cursor": "event_time",
                "cursor_type": "timestamp",
                "cursor_grain": "day",
                "cursor_inputs": {
                    "events": {
                        "column": "event_time",
                        "roles": ["filter", "watermark"],
                    }
                },
                "batch_size": test_case.batch_size,
                "lookback": test_case.lookback,
                "microbatch_limit": {
                    "max_batches": test_case.max_batches,
                    "action": test_case.action,
                },
            }
        ),
        model_name="events",
        ref_count=1,
        known_input_names=frozenset({"events"}),
    )


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchRedesignBehaviorTestCase(
            description="any uses furthest watermark", expected_outcome="2026-07-21"
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_any_watermarks_when_computing_bounds_then_furthest_usable_input_wins(
    test_case: MicrobatchRedesignBehaviorTestCase,
) -> None:
    bounds: CursorBounds | None = compute_cursor_bounds(
        cursor_snapshot=ModelCursorSnapshot(
            target_max="2026-07-15",
            upstream_mins=("2026-07-01", "2026-07-02"),
            upstream_maxes=("2026-07-16", "2026-07-20"),
            cursor_watermark_mode="any",
        ),
        cursor_type="timestamp",
        cursor_start="2026-01-01",
        lookback=None,
        backfill_duration=None,
        start_cursor_override=None,
        end_cursor_override=None,
        is_microbatch=False,
        cursor_grain="day",
    )

    assert bounds is not None
    assert bounds.end == test_case.expected_outcome


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchRedesignBehaviorTestCase(
            description="empty terminal domain", expected_outcome="2025-12-01"
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_empty_terminal_model_when_computing_bounds_then_cursor_end_is_available(
    test_case: MicrobatchRedesignBehaviorTestCase,
) -> None:
    bounds: CursorBounds | None = compute_cursor_bounds(
        cursor_snapshot=ModelCursorSnapshot(
            target_max=None,
            upstream_mins=(),
            upstream_maxes=(),
            upstream_terminal_starts=("2025-01-01",),
            upstream_terminal_ends=("2025-12-01",),
        ),
        cursor_type="timestamp",
        cursor_start="2025-01-01",
        lookback=None,
        backfill_duration=None,
        start_cursor_override=None,
        end_cursor_override=None,
        is_microbatch=False,
        cursor_grain="day",
    )

    assert bounds is not None
    assert bounds.start == "2025-01-01T00:00:00"
    assert bounds.end == test_case.expected_outcome


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchRedesignBehaviorTestCase(
            description="all terminal end replaces physical maximum", expected_outcome="2025-12-01"
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_nonempty_terminal_and_live_inputs_when_mode_all_then_terminal_end_replaces_physical_max(
    test_case: MicrobatchRedesignBehaviorTestCase,
) -> None:
    bounds: CursorBounds | None = compute_cursor_bounds(
        cursor_snapshot=ModelCursorSnapshot(
            target_max="2025-11-01",
            upstream_mins=("2025-01-01", "2026-01-01"),
            upstream_maxes=("2025-11-15", "2026-07-02"),
            upstream_end_inputs=(
                ("2025-11-15", "2025-12-01"),
                ("2026-07-02", None),
            ),
            cursor_watermark_mode="all",
        ),
        cursor_type="timestamp",
        cursor_start="2025-01-01",
        lookback=None,
        backfill_duration=None,
        start_cursor_override=None,
        end_cursor_override=None,
        is_microbatch=False,
        cursor_grain="day",
    )

    assert bounds is not None
    assert bounds.end == test_case.expected_outcome


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchRedesignBehaviorTestCase(
            description="any live end wins", expected_outcome="2026-07-03"
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_nonempty_terminal_and_live_inputs_when_mode_any_then_live_end_wins(
    test_case: MicrobatchRedesignBehaviorTestCase,
) -> None:
    bounds: CursorBounds | None = compute_cursor_bounds(
        cursor_snapshot=ModelCursorSnapshot(
            target_max="2025-11-01",
            upstream_mins=("2025-01-01", "2026-01-01"),
            upstream_maxes=("2026-02-01", "2026-07-02"),
            upstream_end_inputs=(
                ("2026-02-01", "2025-12-01"),
                ("2026-07-02", None),
            ),
            cursor_watermark_mode="any",
        ),
        cursor_type="timestamp",
        cursor_start="2025-01-01",
        lookback=None,
        backfill_duration=None,
        start_cursor_override=None,
        end_cursor_override=None,
        is_microbatch=False,
        cursor_grain="day",
    )

    assert bounds is not None
    assert bounds.end == test_case.expected_outcome


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchRedesignBehaviorTestCase(
            description="all mode uses earliest exclusive input availability",
            expected_outcome="2026-04-05T00:00:00",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_precomputed_watermark_availability_when_computing_bounds_then_it_is_not_readvanced(
    test_case: MicrobatchRedesignBehaviorTestCase,
) -> None:
    bounds: CursorBounds | None = compute_cursor_bounds(
        cursor_snapshot=ModelCursorSnapshot(
            target_max="2026-04-04T00:00:00",
            upstream_mins=("2026-04-01T00:00:00",),
            upstream_maxes=("2026-04-04T00:00:00",),
            upstream_availability_ends=("2026-04-05T00:00:00", "2026-05-01T00:00:00"),
            cursor_watermark_mode="all",
        ),
        cursor_type="timestamp",
        cursor_start="2026-04-01T00:00:00",
        lookback=None,
        backfill_duration=None,
        start_cursor_override=None,
        end_cursor_override=None,
        is_microbatch=False,
        cursor_grain="hour",
    )

    assert bounds is not None
    assert bounds.end == test_case.expected_outcome


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchCursorTypeTestCase("timestamp_ntz", "TIMESTAMP_NTZ", "timestamp", True),
        MicrobatchCursorTypeTestCase("datetime2", "DATETIME2", "timestamp", True),
        MicrobatchCursorTypeTestCase("datetime64", "DATETIME64(6)", "timestamp", True),
        MicrobatchCursorTypeTestCase("smalldatetime", "SMALLDATETIME", "timestamp", True),
        MicrobatchCursorTypeTestCase("date", "DATE", "timestamp", True),
        MicrobatchCursorTypeTestCase("date32", "DATE32", "timestamp", True),
        MicrobatchCursorTypeTestCase("bigint", "BIGINT", "integer", True),
        MicrobatchCursorTypeTestCase("mediumint", "MEDIUMINT", "integer", True),
        MicrobatchCursorTypeTestCase("int128", "INT128", "integer", True),
        MicrobatchCursorTypeTestCase("int256", "INT256", "integer", True),
        MicrobatchCursorTypeTestCase("uint", "UINT", "integer", True),
        MicrobatchCursorTypeTestCase("umediumint", "UMEDIUMINT", "integer", True),
        MicrobatchCursorTypeTestCase("decimal zero scale", "DECIMAL(18, 0)", "integer", True),
        MicrobatchCursorTypeTestCase("numeric default scale", "NUMERIC(20)", "integer", True),
        MicrobatchCursorTypeTestCase("number default scale", "NUMBER", "integer", True),
        MicrobatchCursorTypeTestCase("time only rejected", "TIME", "timestamp", False),
        MicrobatchCursorTypeTestCase("scaled decimal rejected", "DECIMAL(18, 2)", "integer", False),
        MicrobatchCursorTypeTestCase("scaled numeric rejected", "NUMERIC(18, 4)", "integer", False),
        MicrobatchCursorTypeTestCase("scaled number rejected", "NUMBER(18, 2)", "integer", False),
        MicrobatchCursorTypeTestCase("integer not timestamp", "BIGINT", "timestamp", False),
        MicrobatchCursorTypeTestCase("timestamp not integer", "TIMESTAMP", "integer", False),
    ),
    ids=lambda case: case.description,
)
def test_given_known_watermark_contract_type_when_validating_then_cursor_domain_must_match(
    test_case: MicrobatchCursorTypeTestCase,
) -> None:
    assert (
        _watermark_type_is_compatible(
            declared_type=test_case.declared_type, cursor_type=test_case.cursor_type
        )
        is test_case.expected_compatible
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
