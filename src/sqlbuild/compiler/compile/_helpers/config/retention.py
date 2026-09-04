"""Time-travel retention policy resolution."""

from __future__ import annotations

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import ResolvedTimeTravelRetention
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.cursor_algebra.constants import DURATION_DAY_UNIT
from sqlbuild.cursor_algebra.models import Duration
from sqlbuild.spec.contracts.models import (
    AuthoredTimeTravelRetention,
    MaterializationDefaultsConfig,
    TargetConfig,
)
from sqlbuild.spec.contracts.types import (
    TimeTravelRetentionSource,
    TimeTravelRetentionValue,
)


def resolve_time_travel_retention(
    *,
    materialized: object | None,
    model_value: object | None,
    materialization_defaults: MaterializationDefaultsConfig,
    target_config: TargetConfig | None,
    model_name: str,
) -> ResolvedTimeTravelRetention:
    """Resolve target, materialization, and model retention precedence."""

    policy: AuthoredTimeTravelRetention | None = (
        target_config.time_travel_retention if target_config is not None else None
    )
    source: TimeTravelRetentionSource | None = (
        TimeTravelRetentionSource.TARGET if policy is not None else None
    )
    if isinstance(materialized, str) and MaterializationType.is_table_backed(
        materialized=materialized
    ):
        materialization_policy: AuthoredTimeTravelRetention | None = getattr(
            materialization_defaults, materialized
        ).time_travel_retention
        if materialization_policy is not None:
            policy = materialization_policy
            source = TimeTravelRetentionSource.MATERIALIZATION
    if model_value is not None:
        if not isinstance(model_value, str):
            raise CompileInputError(
                f"model '{model_name}': time_travel_retention must be a whole-day string like '7d'"
            )
        if model_value != TimeTravelRetentionValue.INHERIT:
            if model_value == TimeTravelRetentionValue.DISABLED:
                policy = AuthoredTimeTravelRetention(unmanaged=True)
            else:
                duration: Duration | None = Duration.parse(model_value)
                if duration is None or duration.units != frozenset({DURATION_DAY_UNIT}):
                    raise CompileInputError(
                        f"model '{model_name}': time_travel_retention must be a whole-day string "
                        "like '7d', 'inherit', or 'disabled'"
                    )
                policy = AuthoredTimeTravelRetention(desired_days=duration.days)
            source = TimeTravelRetentionSource.MODEL
    if policy is None:
        return ResolvedTimeTravelRetention()
    return ResolvedTimeTravelRetention(
        desired_days=policy.desired_days,
        unmanaged=policy.unmanaged,
        source=source,
    )
