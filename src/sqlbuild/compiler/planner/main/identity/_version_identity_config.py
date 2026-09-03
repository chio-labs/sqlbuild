"""Build model config payloads that participate in version identity."""

from __future__ import annotations


def build_version_identity_config(config_values: dict[str, object]) -> dict[str, object]:
    """Return config fields that affect produced model version identity."""

    identity: dict[str, object] = {}
    legacy_filter_inputs: object | None = config_values.get("cursor_inputs")
    filter_inputs: object | None = config_values.get("cursor_filter_inputs", legacy_filter_inputs)
    watermark_inputs: object | None = config_values.get("cursor_watermark_inputs", filter_inputs)
    if filter_inputs is not None:
        identity["cursor_filter_inputs"] = filter_inputs
        identity["cursor_watermark_inputs"] = watermark_inputs
    version_identity_config_keys: tuple[str, ...] = (
        "append_cursor_inclusive",
        "batch_size",
        "check_columns",
        "cursor",
        "cursor_grain",
        "cursor_start",
        "cursor_start_max_ahead",
        "cursor_start_max_action",
        "cursor_future_max_distance",
        "cursor_future_action",
        "cursor_type",
        "historical_input",
        "incremental_mode",
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
