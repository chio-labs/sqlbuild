"""Minimal projects whose layered model config fails a model config validator."""

from scripts.compiler_differential._helpers.corpus.case_builder import (
    config_files,
    failure_case,
    mart_body_files,
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

    return (
        *_layering_cases(),
        *_incremental_cases(),
        *_materialization_cases(),
        *_template_cases(),
        *_header_metadata_cases(),
        *_combined_fault_cases(),
    )


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


def _template_cases() -> tuple[FailureCase, ...]:
    return (
        failure_case(
            name="config-template-unknown-variable",
            expected_code="P001",
            expected_message="model config references unknown variable 'missing_region'",
            files=_staging_header('  schema "${missing_region}_core",'),
        ),
        failure_case(
            name="config-template-unsupported-function",
            expected_code="P001",
            expected_message="references unsupported template function 'upper'",
            files=_staging_header("  alias \"${upper('orders')}\","),
        ),
        failure_case(
            name="config-template-unterminated-string",
            expected_code="P001",
            expected_message="unterminated single-quoted string at position 9",
            files=_staging_header('  alias "${coalesce(\'orders)}",'),
        ),
        failure_case(
            name="config-template-wrong-argument-count",
            expected_code="P001",
            expected_message="model config if(...) expects 3 arguments",
            files=_staging_header("  alias \"${if(true, 'orders')}\","),
        ),
        failure_case(
            name="config-template-missing-environment-variable",
            expected_code="P001",
            expected_message="references missing ENV variable 'SQB_CORPUS_UNSET_SCHEMA'",
            files=_staging_header('  schema "${ENV:SQB_CORPUS_UNSET_SCHEMA}",'),
        ),
        failure_case(
            name="config-template-unknown-namespace",
            expected_code="P001",
            expected_message="references unsupported template namespace 'VAULT'",
            files=_staging_header('  alias "${VAULT:orders}",'),
        ),
    )


def _header_metadata_cases() -> tuple[FailureCase, ...]:
    return (
        failure_case(
            name="header-column-unknown-metadata-key",
            expected_code="P001",
            expected_message="column 'order_id' has unknown metadata keys: format",
            files=_staging_header("  columns (order_id (type INTEGER, format plain)),"),
        ),
        failure_case(
            name="header-duplicate-column",
            expected_code="P001",
            expected_message="has duplicate column 'ORDER_ID'",
            files=_staging_header("  columns (order_id (type INTEGER), ORDER_ID (type INTEGER)),"),
        ),
        failure_case(
            name="header-column-type-not-text",
            expected_code="P001",
            expected_message="column 'order_id' 'type' must be a non-empty string",
            files=_staging_header("  columns (order_id (type 5)),"),
        ),
        failure_case(
            name="header-audit-severity",
            expected_code="P001",
            expected_message="'severity' must be one of: warn, error",
            files=_staging_header(
                "  audits [unique_combination (columns [order_id], severity fatal)],"
            ),
        ),
        failure_case(
            name="header-audit-identity",
            expected_code="D016",
            expected_message="Invalid model audit definition identity 'NotNull'",
            files=_staging_header("  audits [NotNull],"),
        ),
        failure_case(
            name="header-column-audits-not-a-list",
            expected_code="P001",
            expected_message="column 'order_id' audits must be a list",
            files=_staging_header("  columns (order_id (audits not_null)),"),
        ),
    )


def _combined_fault_cases() -> tuple[FailureCase, ...]:
    return (
        failure_case(
            name="config-several-faults-reports-the-first",
            expected_code="P001",
            expected_message="table_type must be permanent, transient, or inherit",
            files=_staging_header(
                "  materialized incremental,\n  incremental_strategy upsert,\n"
                "  cursor_type date,\n  contract strict,\n  table_type temporary,"
            ),
        ),
        failure_case(
            name="config-cursor-bound-outside-utc-years",
            expected_code="P001",
            expected_message="falls outside years 1-9999 once converted to UTC",
            files=_staging_header(
                "  materialized incremental,\n  incremental_strategy append,\n"
                "  cursor placed_at,\n  cursor_type timestamp,\n  cursor_grain day,\n"
                "  cursor_start '0001-01-01T00:00:00+01:00',\n  cursor_end '2024-01-01',"
            ),
        ),
        failure_case(
            name="config-unknown-model-reference",
            expected_code="P001",
            expected_message="references unknown model 'stg_refunds'",
            files=mart_body_files(
                "SELECT customer_id, SUM(amount) AS total_amount\n"
                'FROM __ref("stg_refunds")\nGROUP BY customer_id\n'
            ),
        ),
        failure_case(
            name="config-placeholder-on-built-in-materialization",
            expected_code="P001",
            expected_message="@@@placeholders are only allowed on custom materializations",
            files=staging_files(
                'MODEL (\n  description "Staged orders",\n);\n\n'
                "SELECT order_id, customer_id, amount, status\n"
                'FROM __source("raw_orders")\nWHERE status = @@@status\n'
            ),
        ),
    )
