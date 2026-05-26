"""Build model config payloads that participate in version identity."""

from __future__ import annotations


def build_version_identity_config(config_values: dict[str, object]) -> dict[str, object]:
    """Return config fields that affect produced model version identity.

    Validation/readiness concerns such as audits and contracts are intentionally
    excluded unless they affect the produced physical version identity.
    """

    version_identity_config_keys: tuple[str, ...] = (
        "append_cursor_inclusive",
        "check_columns",
        "cursor",
        "cursor_grain",
        "cursor_inputs",
        "cursor_start",
        "cursor_type",
        "historical_input",
        "incremental_mode",
        "incremental_strategy",
        "initial_valid_from",
        "invalidate_hard_deletes",
        "lookback",
        "materialized",
        "observed_at",
        "on_schema_change",
        "query_change_backfill",
        "schema_change_backfill",
        "snapshot_full_refresh",
        "snapshot_schema_change",
        "snapshot_strategy",
        "unique_key",
        "updated_at",
        "valid_from_column",
        "valid_to_column",
    )
    return {key: config_values[key] for key in version_identity_config_keys if key in config_values}
