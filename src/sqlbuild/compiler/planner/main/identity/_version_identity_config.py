"""Build model config payloads that participate in version identity."""

from __future__ import annotations

from sqlbuild.compiler.compile.constants import CURSOR_INPUTS_CONFIG_KEY


def build_version_identity_config(config_values: dict[str, object]) -> dict[str, object]:
    """Return config fields that affect produced model version identity."""

    identity: dict[str, object] = {}
    if CURSOR_INPUTS_CONFIG_KEY in config_values:
        identity[CURSOR_INPUTS_CONFIG_KEY] = config_values[CURSOR_INPUTS_CONFIG_KEY]
    version_identity_config_keys: tuple[str, ...] = (
        "append_cursor_inclusive",
        "batch_size",
        "check_columns",
        "cursor",
        "cursor_grain",
        "cursor_start",
        "cursor_end",
        "cursor_start_max_ahead",
        "cursor_start_max_action",
        "cursor_future_max_distance",
        "cursor_future_action",
        "cursor_type",
        "historical_input",
        "incremental_mode",
        "microbatch_strategy",
        "cursor_watermark_mode",
        "max_microbatches",
        "incremental_strategy",
        "merge_exclude_columns",
        "full_refresh",
        "initial_valid_from",
        "invalidate_hard_deletes",
        "lookback",
        "materialized",
        "observed_at",
        "on_schema_change",
        "snapshot_full_refresh",
        "snapshot_schema_change",
        "snapshot_strategy",
        "unique_key",
        "updated_at",
        "valid_from_column",
        "valid_to_column",
    )
    identity.update(
        {key: config_values[key] for key in version_identity_config_keys if key in config_values}
    )
    return identity
