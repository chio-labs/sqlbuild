"""Minimal projects whose layered model config fails a model config validator."""

from scripts.compiler_differential._helpers.corpus.case_builder import (
    config_files,
    failure_case,
    staging_files,
)
from scripts.compiler_differential.constants import FAILURE_BASE_STAGING
from scripts.compiler_differential.models import FailureCase

_STAGING_HEADER: str = '"Staged orders",'
_INCREMENTAL: str = (
    "  materialized incremental,\n  incremental_strategy delete_insert,\n"
    "  cursor order_id,\n  cursor_type integer,\n"
)
_WATERMARK: str = (
    "  materialized incremental,\n  incremental_strategy delete_insert,\n"
    "  cursor placed_at,\n  cursor_type timestamp,\n  cursor_grain day,\n"
    "  incremental_mode microbatch,\n  microbatch_strategy watermark,\n"
    "  cursor_watermark_mode all,\n  batch_size 1d,\n"
    "  cursor_inputs (raw_orders (column placed_at, roles [filter, watermark])),\n"
)


def _staging_header(extra: str) -> dict[str, str]:
    return staging_files(
        FAILURE_BASE_STAGING.replace(_STAGING_HEADER, f"{_STAGING_HEADER}\n{extra}")
    )


def config_failure_cases() -> tuple[FailureCase, ...]:
    """Return the model config validator failure cases in a stable order."""

    return (*_layering_cases(), *_incremental_cases(), *_materialization_cases())


def _layering_cases() -> tuple[FailureCase, ...]:
    return (
        failure_case(
            name="config-header-tags-not-list",
            expected_code="P001",
            expected_message="tags must be a list",
            files=_staging_header('  tags "orders",'),
        ),
        failure_case(
            name="config-untyped-hook-entry",
            expected_code="P001",
            expected_message="entries must use typed",
            files=config_files('\n[path_defaults.staging]\npre_hooks = ["SELECT 1"]\n'),
        ),
        failure_case(
            name="config-macro-outside-hooks",
            expected_code="P001",
            expected_message="does not allow macros",
            files=_staging_header('  alias "@cents(amount)",'),
        ),
        failure_case(
            name="config-unknown-table-type",
            expected_code="P001",
            expected_message="table_type must be permanent",
            files=_staging_header("  materialized table,\n  table_type temporary,"),
        ),
        failure_case(
            name="config-retention-not-whole-days",
            expected_code="P001",
            expected_message="whole-day string",
            files=_staging_header("  materialized table,\n  time_travel_retention 6h,"),
        ),
        failure_case(
            name="config-equally-specific-path-defaults",
            expected_code="D007",
            expected_message="equally specific path_defaults keys",
            files=config_files(
                '\n[path_defaults."*/stg_orders.sql"]\nmaterialized = "table"\n'
                '\n[path_defaults."staging/*"]\nmaterialized = "view"\n'
            ),
        ),
    )


def _incremental_cases() -> tuple[FailureCase, ...]:
    return (
        failure_case(
            name="config-incremental-without-strategy",
            expected_code="P001",
            expected_message="requires incremental_strategy",
            files=_staging_header("  materialized incremental,"),
        ),
        failure_case(
            name="config-cursor-bounds-reversed",
            expected_code="P001",
            expected_message="cursor_start must be before exclusive cursor_end",
            files=_staging_header(f"{_INCREMENTAL}  cursor_start 20,\n  cursor_end 10,"),
        ),
        failure_case(
            name="config-microbatch-without-strategy",
            expected_code="P001",
            expected_message="requires explicit microbatch_strategy",
            files=_staging_header(f"{_INCREMENTAL}  incremental_mode microbatch,"),
        ),
        failure_case(
            name="config-watermark-limit-below-lookback",
            expected_code="P001",
            expected_message="below the ordinary lookback requirement",
            files=_staging_header(f"{_WATERMARK}  lookback 3d,\n  max_microbatches 2,"),
        ),
        failure_case(
            name="config-concurrency-without-capability",
            expected_code="P001",
            expected_message="batch_concurrency > 1 requires",
            files=_staging_header(f"{_INCREMENTAL}  batch_concurrency 2,"),
        ),
        failure_case(
            name="config-merge-exclusion-overlaps-key",
            expected_code="P001",
            expected_message="cannot include unique_key",
            files=_staging_header(
                "  materialized incremental,\n  incremental_strategy merge,\n"
                "  unique_key [order_id],\n  merge_exclude_columns [ORDER_ID],"
            ),
        ),
    )


def _materialization_cases() -> tuple[FailureCase, ...]:
    return (
        failure_case(
            name="config-unknown-materialization",
            expected_code="P001",
            expected_message="unknown materialization 'archive'",
            files=_staging_header("  materialized archive,"),
        ),
        failure_case(
            name="config-unknown-contract",
            expected_code="P001",
            expected_message="unknown contract 'strict'",
            files=_staging_header("  contract strict,"),
        ),
        failure_case(
            name="config-incremental-key-on-table",
            expected_code="P001",
            expected_message="only valid for incremental models",
            files=_staging_header("  materialized table,\n  on_schema_change fail,"),
        ),
        failure_case(
            name="config-snapshot-without-unique-key",
            expected_code="P001",
            expected_message="snapshot materialization requires unique_key",
            files=_staging_header("  materialized snapshot,\n  snapshot_strategy check,"),
        ),
        failure_case(
            name="config-retention-on-view",
            expected_code="P001",
            expected_message="not valid for views",
            files=_staging_header("  materialized view,\n  time_travel_retention 7d,"),
        ),
        failure_case(
            name="config-migrate-force-on-table",
            expected_code="P001",
            expected_message="migrate_force is only valid",
            files=_staging_header(
                "  materialized table,\n  migrate_from legacy_orders,\n  migrate_force true,"
            ),
        ),
        failure_case(
            name="config-old-name-view-without-duration",
            expected_code="P001",
            expected_message="old_name_view must be a positive duration",
            files=_staging_header("  materialized table,\n  old_name_view soon,"),
        ),
    )
