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
_ROLLING: str = (
    _WATERMARK.replace("microbatch_strategy watermark", "microbatch_strategy rolling_window")
    .replace("  cursor_watermark_mode all,\n", "")
    .replace("(raw_orders (column placed_at, roles [filter, watermark]))", "(raw_orders placed_at)")
    + "  lookback 1d,\n"
)
_BEYOND_64_BITS: int = 2**64
_INT64_MAX: int = 2**63 - 1


def _header_help(purpose: str, entry: str) -> str:
    indent: str = " " * 12
    return (
        f"{purpose}, add this to the MODEL header:\n{indent}MODEL (\n"
        f"{indent}  {entry},\n{indent}  ...\n{indent});"
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
        *_integer_range_cases(),
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


def _integer_range_cases() -> tuple[FailureCase, ...]:
    return (
        failure_case(
            name="config-cursor-start-below-64-bits",
            expected_code="P001",
            expected_message=f"cursor_start -{_BEYOND_64_BITS} is smaller than a 64-bit integer",
            expected_help=_header_help(
                "set cursor_start to a value that fits in 64 bits",
                f"cursor_start {-_INT64_MAX - 1}",
            ),
            files=_staging_header(f"{_INCREMENTAL}  cursor_start -{_BEYOND_64_BITS},"),
        ),
        failure_case(
            name="config-batch-concurrency-beyond-64-bits",
            expected_code="P001",
            expected_message=f"batch_concurrency {_BEYOND_64_BITS} is larger than a 64-bit integer",
            expected_help=_header_help(
                "set batch_concurrency to a value that fits in 64 bits",
                f"batch_concurrency {_INT64_MAX}",
            ),
            files=_staging_header(f"{_WATERMARK}  batch_concurrency {_BEYOND_64_BITS},"),
        ),
        failure_case(
            name="config-max-microbatches-beyond-64-bits",
            expected_code="P001",
            expected_message=f"max_microbatches {_BEYOND_64_BITS} is larger than a 64-bit integer",
            expected_help=_header_help(
                "set max_microbatches to a value that fits in 64 bits",
                f"max_microbatches {_INT64_MAX}",
            ),
            files=_staging_header(f"{_WATERMARK}  max_microbatches {_BEYOND_64_BITS},"),
        ),
        failure_case(
            name="config-microbatch-limit-beyond-64-bits",
            expected_code="P001",
            expected_message=(
                f"microbatch_limit max_batches {_BEYOND_64_BITS} is larger than a 64-bit integer"
            ),
            expected_help=_header_help(
                "set microbatch_limit max_batches to a value that fits in 64 bits",
                f"microbatch_limit (max_batches {_INT64_MAX}, action error)",
            ),
            files=_staging_header(
                f"{_WATERMARK}  microbatch_limit (max_batches {_BEYOND_64_BITS}, action error),"
            ),
        ),
        failure_case(
            name="config-rolling-max-microbatches-beyond-64-bits",
            expected_code="P001",
            expected_message="max_microbatches is only valid with microbatch_strategy=watermark",
            files=_staging_header(f"{_ROLLING}  max_microbatches {_BEYOND_64_BITS},"),
        ),
        failure_case(
            name="config-rolling-microbatch-limit-beyond-64-bits",
            expected_code="P001",
            expected_message="microbatch_limit is only valid with microbatch_strategy=watermark",
            files=_staging_header(
                f"{_ROLLING}  microbatch_limit (max_batches {_BEYOND_64_BITS}, action error),"
            ),
        ),
        failure_case(
            name="config-lookback-beyond-64-bits",
            expected_code="P001",
            expected_message=(
                "lookback '99999999999999999999d' has a number larger than a 64-bit integer"
            ),
            expected_help=_header_help(
                "use a lookback whose numbers fit in 64 bits", "lookback '7d'"
            ),
            files=_staging_header(f"{_INCREMENTAL}  lookback 99999999999999999999d,"),
        ),
        failure_case(
            name="config-batch-size-beyond-64-bits",
            expected_code="P001",
            expected_message=(
                "batch_size '99999999999999999999d' has a number larger than a 64-bit integer"
            ),
            expected_help=_header_help(
                "use a batch_size whose numbers fit in 64 bits", "batch_size '7d'"
            ),
            files=_staging_header(
                _WATERMARK.replace("batch_size 1d", "batch_size 99999999999999999999d")
            ),
        ),
        failure_case(
            name="header-audit-minimum-samples-beyond-64-bits",
            expected_code="P001",
            expected_message=(
                f"audit 'not_null' 'minimum_samples' {_BEYOND_64_BITS} is larger than a 64-bit "
                "integer"
            ),
            expected_help=_header_help(
                "set minimum_samples to a value that fits in 64 bits",
                f"audits [not_null (minimum_samples {_INT64_MAX})]",
            ),
            files=_staging_header(f"  audits [not_null (minimum_samples {_BEYOND_64_BITS})],"),
        ),
        failure_case(
            name="header-column-audit-evidence-limit-beyond-64-bits",
            expected_code="P001",
            expected_message=(
                f"column 'order_id' audit 'not_null' 'evidence_limit' {_BEYOND_64_BITS} is larger "
                "than a 64-bit integer"
            ),
            expected_help=_header_help(
                "set evidence_limit to a value that fits in 64 bits",
                f"columns (order_id (audits [not_null (evidence_limit {_INT64_MAX})]))",
            ),
            files=_staging_header(
                f"  columns (order_id (audits [not_null (evidence_limit {_BEYOND_64_BITS})])),"
            ),
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
