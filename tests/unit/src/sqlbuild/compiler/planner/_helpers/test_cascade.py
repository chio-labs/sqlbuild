"""Tests for backfill cascade propagation."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner._helpers.changes.policy import resolve_replay_on_change
from sqlbuild.compiler.planner._helpers.pruning.cascade import (
    build_self_cascade,
    resolve_cascade,
)
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    CascadeResult,
)
from sqlbuild.compiler.planner.types import BackfillAction, PlanReason
from tests.unit.src.sqlbuild.compiler.planner._helpers._test_types import (
    ResolveCascadeRootCauseTestCase,
    ResolveCascadeTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.helpers import (
    build_cascade_upstream_state,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveCascadeTestCase(
            description="upstream full cascades to same cursor type downstream",
            own_action=BackfillAction.FORWARD_ONLY,
            own_duration=None,
            own_cursor_type="timestamp",
            upstream_entries=(("orders", BackfillAction.FULL, None, "timestamp"),),
            expected_cascade=True,
            expected_action=BackfillAction.FULL,
            expected_root_cause="orders",
            expected_cause_count=1,
        ),
        ResolveCascadeTestCase(
            description="upstream bounded cascades to same cursor type downstream",
            own_action=BackfillAction.FORWARD_ONLY,
            own_duration=None,
            own_cursor_type="timestamp",
            upstream_entries=(("orders", BackfillAction.BOUNDED, "90d", "timestamp"),),
            expected_cascade=True,
            expected_action=BackfillAction.BOUNDED,
            expected_duration="90d",
            expected_root_cause="orders",
            expected_cause_count=1,
        ),
        ResolveCascadeTestCase(
            description="upstream full cascades across cursor types",
            own_action=BackfillAction.FORWARD_ONLY,
            own_duration=None,
            own_cursor_type="integer",
            upstream_entries=(("orders", BackfillAction.FULL, None, "timestamp"),),
            expected_cascade=True,
            expected_action=BackfillAction.FULL,
            expected_root_cause="orders",
            expected_cause_count=1,
        ),
        ResolveCascadeTestCase(
            description="picks most aggressive upstream when multiple cascade",
            own_action=BackfillAction.FORWARD_ONLY,
            own_duration=None,
            own_cursor_type="timestamp",
            upstream_entries=(
                ("orders", BackfillAction.BOUNDED, "30d", "timestamp"),
                ("payments", BackfillAction.BOUNDED, "90d", "timestamp"),
            ),
            expected_cascade=True,
            expected_action=BackfillAction.BOUNDED,
            expected_duration="90d",
            expected_root_cause="payments",
            expected_cause_count=2,
        ),
        ResolveCascadeTestCase(
            description="alphabetical tiebreak among equal upstream windows",
            own_action=BackfillAction.FORWARD_ONLY,
            own_duration=None,
            own_cursor_type="timestamp",
            upstream_entries=(
                ("orders", BackfillAction.BOUNDED, "90d", "timestamp"),
                ("customers", BackfillAction.BOUNDED, "90d", "timestamp"),
            ),
            expected_cascade=True,
            expected_action=BackfillAction.BOUNDED,
            expected_duration="90d",
            expected_root_cause="customers",
            expected_cause_count=2,
        ),
        ResolveCascadeTestCase(
            description="full beats bounded in upstream comparison",
            own_action=BackfillAction.FORWARD_ONLY,
            own_duration=None,
            own_cursor_type="timestamp",
            upstream_entries=(
                ("orders", BackfillAction.BOUNDED, "90d", "timestamp"),
                ("payments", BackfillAction.FULL, None, "timestamp"),
            ),
            expected_cascade=True,
            expected_action=BackfillAction.FULL,
            expected_root_cause="payments",
            expected_cause_count=2,
        ),
        ResolveCascadeTestCase(
            description="local bounded policy replaces stronger upstream full",
            own_action=BackfillAction.FORWARD_ONLY,
            own_duration=None,
            own_cursor_type="timestamp",
            upstream_entries=(
                ("orders", BackfillAction.FULL, None, "timestamp"),
                ("customers", BackfillAction.BOUNDED, "30d", "timestamp"),
            ),
            local_policy="bounded-1d",
            expected_cascade=True,
            expected_action=BackfillAction.BOUNDED,
            expected_duration="1d",
            expected_root_cause="orders",
            expected_cause_count=2,
        ),
        ResolveCascadeTestCase(
            description="local full policy replaces weaker upstream bounded",
            own_action=BackfillAction.FORWARD_ONLY,
            own_duration=None,
            own_cursor_type="timestamp",
            upstream_entries=(("orders", BackfillAction.BOUNDED, "30d", "timestamp"),),
            local_policy="full",
            expected_cascade=True,
            expected_action=BackfillAction.FULL,
            expected_root_cause="orders",
            expected_cause_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_upstream_cascade_when_resolving_then_returns_cascade_result(
    test_case: ResolveCascadeTestCase,
) -> None:
    upstream_keys: tuple[CompiledObjectKey, ...]
    effective_cascades: dict[str, CascadeResult]
    model_cursor_types: dict[str, str | None]
    upstream_keys, effective_cascades, model_cursor_types = build_cascade_upstream_state(
        test_case.upstream_entries
    )

    result: CascadeResult | None = resolve_cascade(
        model_name="test_model",
        own_backfill=BackfillResult(action=test_case.own_action, duration=test_case.own_duration),
        local_backfill=resolve_replay_on_change(replay_on_change=test_case.local_policy),
        own_cursor_type=test_case.own_cursor_type,
        upstream_keys=upstream_keys,
        effective_cascades=effective_cascades,
        model_cursor_types=model_cursor_types,
    )

    assert result is not None
    assert result.effective_action == test_case.expected_action
    assert result.effective_duration == test_case.expected_duration
    assert result.root_cause == test_case.expected_root_cause
    assert len(result.causes) == test_case.expected_cause_count


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveCascadeTestCase(
            description="no upstream produces no cascade",
            own_action=BackfillAction.FORWARD_ONLY,
            own_duration=None,
            own_cursor_type="timestamp",
            upstream_entries=(),
            expected_cascade=False,
        ),
        ResolveCascadeTestCase(
            description="upstream forward produces no cascade",
            own_action=BackfillAction.FORWARD_ONLY,
            own_duration=None,
            own_cursor_type="timestamp",
            upstream_entries=(("orders", BackfillAction.FORWARD_ONLY, None, "timestamp"),),
            expected_cascade=False,
        ),
        ResolveCascadeTestCase(
            description="upstream bounded does not cascade across cursor types",
            own_action=BackfillAction.FORWARD_ONLY,
            own_duration=None,
            own_cursor_type="integer",
            upstream_entries=(("orders", BackfillAction.BOUNDED, "90d", "timestamp"),),
            expected_cascade=False,
        ),
        ResolveCascadeTestCase(
            description="upstream weaker than own backfill produces no cascade",
            own_action=BackfillAction.BOUNDED,
            own_duration="90d",
            own_cursor_type="timestamp",
            upstream_entries=(("orders", BackfillAction.BOUNDED, "30d", "timestamp"),),
            expected_cascade=False,
        ),
        ResolveCascadeTestCase(
            description="own bounded backfill replaces stronger upstream bounded",
            own_action=BackfillAction.BOUNDED,
            own_duration="30d",
            own_cursor_type="timestamp",
            upstream_entries=(("orders", BackfillAction.BOUNDED, "90d", "timestamp"),),
            expected_cascade=False,
        ),
        ResolveCascadeTestCase(
            description="own full is not exceeded by upstream bounded",
            own_action=BackfillAction.FULL,
            own_duration=None,
            own_cursor_type="timestamp",
            upstream_entries=(("orders", BackfillAction.BOUNDED, "90d", "timestamp"),),
            expected_cascade=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_no_stronger_upstream_when_resolving_then_returns_none(
    test_case: ResolveCascadeTestCase,
) -> None:
    upstream_keys: tuple[CompiledObjectKey, ...]
    effective_cascades: dict[str, CascadeResult]
    model_cursor_types: dict[str, str | None]
    upstream_keys, effective_cascades, model_cursor_types = build_cascade_upstream_state(
        test_case.upstream_entries
    )

    result: CascadeResult | None = resolve_cascade(
        model_name="test_model",
        own_backfill=BackfillResult(action=test_case.own_action, duration=test_case.own_duration),
        local_backfill=resolve_replay_on_change(replay_on_change=test_case.local_policy),
        own_cursor_type=test_case.own_cursor_type,
        upstream_keys=upstream_keys,
        effective_cascades=effective_cascades,
        model_cursor_types=model_cursor_types,
    )

    assert result is None
    assert not test_case.expected_cascade


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveCascadeTestCase(
            description="build_self_cascade preserves own backfill in accumulator",
            own_action=BackfillAction.BOUNDED,
            own_duration="30d",
            own_cursor_type="timestamp",
            upstream_entries=(),
            expected_cascade=False,
            expected_action=BackfillAction.BOUNDED,
            expected_duration="30d",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_own_backfill_when_building_self_cascade_then_preserves_values(
    test_case: ResolveCascadeTestCase,
) -> None:
    result: CascadeResult = build_self_cascade(
        backfill=BackfillResult(action=test_case.own_action, duration=test_case.own_duration)
    )

    assert result.effective_action == test_case.expected_action
    assert result.effective_duration == test_case.expected_duration
    assert result.root_cause is None
    assert result.causes == ()


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveCascadeRootCauseTestCase(
            description="multihop cascade preserves function root cause",
            expected_action=BackfillAction.FULL,
            expected_root_cause="is_completed_order",
            expected_root_reason=PlanReason.QUERY_CHANGED,
            expected_immediate_cause="hourly_order_activity",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_multihop_cascade_when_resolving_then_preserves_root_cause(
    test_case: ResolveCascadeRootCauseTestCase,
) -> None:
    hourly_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL, name="hourly_order_activity"
    )
    upstream_keys: tuple[CompiledObjectKey, ...] = (hourly_key,)
    effective_cascades: dict[str, CascadeResult] = {
        "hourly_order_activity": build_self_cascade(
            backfill=BackfillResult(action=BackfillAction.FULL),
            root_cause="is_completed_order",
            root_reason=PlanReason.QUERY_CHANGED,
        )
    }
    model_cursor_types: dict[str, str | None] = {"hourly_order_activity": "timestamp"}

    result: CascadeResult | None = resolve_cascade(
        model_name="daily_activity_rollup",
        own_backfill=BackfillResult(action=BackfillAction.FORWARD_ONLY),
        local_backfill=BackfillResult(action=BackfillAction.FORWARD_ONLY),
        own_cursor_type="timestamp",
        upstream_keys=upstream_keys,
        effective_cascades=effective_cascades,
        model_cursor_types=model_cursor_types,
    )

    assert result is not None
    assert result.effective_action == test_case.expected_action
    assert result.root_cause == test_case.expected_root_cause
    assert result.root_reason == test_case.expected_root_reason
    assert result.causes[0].model_name == test_case.expected_immediate_cause
