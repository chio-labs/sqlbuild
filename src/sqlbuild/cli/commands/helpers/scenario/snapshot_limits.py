"""Scenario snapshot capture limit helpers."""

from __future__ import annotations

from sqlbuild.cli.commands.helpers.scenario.constants import (
    DEFAULT_MAX_SNAPSHOT_BYTES_PER_RELATION,
    DEFAULT_MAX_SNAPSHOT_ROWS_PER_RELATION,
    DEFAULT_MAX_SNAPSHOT_TOTAL_BYTES,
    DEFAULT_MAX_SNAPSHOT_TOTAL_ROWS,
)
from sqlbuild.cli.commands.helpers.scenario.models import ScenarioSnapshotLimitInputs
from sqlbuild.executor.scenario.models import ScenarioSnapshotCaptureLimits
from sqlbuild.spec.models.project import ScenarioConfig


def build_scenario_snapshot_capture_limits(
    *,
    scenario_config: ScenarioConfig,
    limit_inputs: ScenarioSnapshotLimitInputs,
) -> ScenarioSnapshotCaptureLimits:
    """Build scenario snapshot capture limits from CLI options."""

    return ScenarioSnapshotCaptureLimits(
        max_rows_per_relation=_resolve_limit(
            cli_value=limit_inputs.max_snapshot_rows,
            config_value=scenario_config.snapshot_limits.max_rows_per_relation,
            default_value=DEFAULT_MAX_SNAPSHOT_ROWS_PER_RELATION,
        ),
        max_total_rows=_resolve_limit(
            cli_value=limit_inputs.max_snapshot_total_rows,
            config_value=scenario_config.snapshot_limits.max_total_rows,
            default_value=DEFAULT_MAX_SNAPSHOT_TOTAL_ROWS,
        ),
        max_bytes_per_relation=_resolve_limit(
            cli_value=limit_inputs.max_snapshot_bytes,
            config_value=scenario_config.snapshot_limits.max_bytes_per_relation,
            default_value=DEFAULT_MAX_SNAPSHOT_BYTES_PER_RELATION,
        ),
        max_total_bytes=_resolve_limit(
            cli_value=limit_inputs.max_snapshot_total_bytes,
            config_value=scenario_config.snapshot_limits.max_total_bytes,
            default_value=DEFAULT_MAX_SNAPSHOT_TOTAL_BYTES,
        ),
        force=limit_inputs.force,
    )


def _resolve_limit(*, cli_value: int | None, config_value: int | None, default_value: int) -> int:
    if cli_value is not None:
        return cli_value
    if config_value is not None:
        return config_value
    return default_value


def scenario_snapshot_capture_warning(*, force: bool) -> str:
    """Return a warning shown before committable snapshot files are written."""

    suffix: str = " Size limits are bypassed." if force else ""
    return (
        "Review captured scenario snapshots before committing; they may contain sensitive "
        f"warehouse data.{suffix}"
    )
