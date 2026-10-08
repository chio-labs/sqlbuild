//! Config keys and vocabularies the Python model validators accept.

/// Built-in materializations that never name a custom materialization.
pub const BUILTIN_MATERIALIZATIONS: [&str; 4] = ["view", "table", "incremental", "snapshot"];
/// Materializations that own a physical managed table.
pub const TABLE_BACKED_MATERIALIZATIONS: [&str; 3] = ["table", "incremental", "snapshot"];
/// Materializations that keep history across runs.
pub const HISTORY_MATERIALIZATIONS: [&str; 2] = ["incremental", "snapshot"];
/// The view materialization.
pub const VIEW_MATERIALIZATION: &str = "view";
/// The table materialization.
pub const TABLE_MATERIALIZATION: &str = "table";
/// The incremental materialization.
pub const INCREMENTAL_MATERIALIZATION: &str = "incremental";
/// The snapshot materialization.
pub const SNAPSHOT_MATERIALIZATION: &str = "snapshot";

/// `IncrementalStrategy` values.
pub const INCREMENTAL_STRATEGIES: [&str; 3] = ["append", "delete_insert", "merge"];
/// The append incremental strategy.
pub const APPEND_STRATEGY: &str = "append";
/// The delete-insert incremental strategy.
pub const DELETE_INSERT_STRATEGY: &str = "delete_insert";
/// The merge incremental strategy.
pub const MERGE_STRATEGY: &str = "merge";
/// `IncrementalMode` values.
pub const INCREMENTAL_MODES: [&str; 2] = ["full", "microbatch"];
/// The microbatch incremental mode.
pub const MICROBATCH_MODE: &str = "microbatch";
/// `MicrobatchStrategy` values.
pub const MICROBATCH_STRATEGIES: [&str; 2] = ["rolling_window", "watermark"];
/// The rolling-window microbatch strategy.
pub const ROLLING_WINDOW_STRATEGY: &str = "rolling_window";
/// The watermark microbatch strategy.
pub const WATERMARK_STRATEGY: &str = "watermark";
/// `CursorWatermarkMode` values.
pub const WATERMARK_MODES: [&str; 2] = ["all", "any"];
/// `CursorInputRole` values.
pub const CURSOR_INPUT_ROLES: [&str; 2] = ["filter", "watermark"];
/// The filter cursor input role.
pub const FILTER_ROLE: &str = "filter";
/// The watermark cursor input role.
pub const WATERMARK_ROLE: &str = "watermark";
/// `CursorType` values.
pub const CURSOR_TYPES: [&str; 2] = ["timestamp", "integer"];
/// The timestamp cursor type.
pub const TIMESTAMP_CURSOR: &str = "timestamp";
/// The integer cursor type.
pub const INTEGER_CURSOR: &str = "integer";
/// `CursorGrain` values with their `GRAIN_BATCH_SIZE` durations.
pub const CURSOR_GRAIN_BATCH_SIZES: [(&str, &str); 6] = [
    ("second", "1s"),
    ("minute", "1m"),
    ("hour", "1h"),
    ("day", "1d"),
    ("month", "1mo"),
    ("year", "1y"),
];
/// `FutureCursorAction` values.
pub const FUTURE_CURSOR_ACTIONS: [&str; 2] = ["cap", "error"];
/// `MicrobatchLimitAction` values.
pub const MICROBATCH_LIMIT_ACTIONS: [&str; 4] = ["cap_from_end", "cap_from_start", "error", "warn"];
/// The cap-from-start microbatch limit action.
pub const CAP_FROM_START_ACTION: &str = "cap_from_start";
/// Accepted `unaccounted_partition_policy` values.
pub const UNACCOUNTED_PARTITION_POLICIES: [&str; 3] =
    ["synthesize", "recover_empty", "recover_all"];
/// `ContractPolicy` values.
pub const CONTRACT_POLICIES: [&str; 2] = ["none", "enforced"];
/// The enforced contract policy.
pub const ENFORCED_CONTRACT: &str = "enforced";
/// `OnSchemaChange` values.
pub const ON_SCHEMA_CHANGE_POLICIES: [&str; 4] =
    ["ignore", "fail", "append_new_columns", "sync_all_columns"];
/// Unbounded `replay_on_change` values.
pub const REPLAY_ON_CHANGE_ACTIONS: [&str; 2] = ["forward", "full"];
/// The prefix of a bounded `replay_on_change` value.
pub const BOUNDED_REPLAY_PREFIX: &str = "bounded-";
/// `SnapshotStrategy` values.
pub const SNAPSHOT_STRATEGIES: [&str; 2] = ["timestamp", "check"];
/// The timestamp snapshot strategy.
pub const TIMESTAMP_SNAPSHOT_STRATEGY: &str = "timestamp";
/// The check snapshot strategy.
pub const CHECK_SNAPSHOT_STRATEGY: &str = "check";
/// `HistoricalInput` values.
pub const HISTORICAL_INPUTS: [&str; 2] = ["snapshot", "changes"];
/// The changes historical input.
pub const CHANGES_HISTORICAL_INPUT: &str = "changes";
/// `InitialValidFrom` values.
pub const INITIAL_VALID_FROM_VALUES: [&str; 3] = ["updated_at", "observed_at", "execution_time"];
/// `SnapshotFullRefreshPolicy` values.
pub const SNAPSHOT_FULL_REFRESH_POLICIES: [&str; 3] = ["deny", "require_confirmation", "allow"];
/// `SnapshotSchemaChangePolicy` values.
pub const SNAPSHOT_SCHEMA_CHANGE_POLICIES: [&str; 3] =
    ["deny", "require_confirmation", "append_new_columns"];
/// The snapshot schema-change policy that conflicts with an enforced contract.
pub const APPEND_NEW_COLUMNS_POLICY: &str = "append_new_columns";
/// The `on_schema_change` value the change-policy help shows.
pub const ON_SCHEMA_CHANGE_EXAMPLE: &str = "append_new_columns";
/// The `replay_on_change` value the change-policy help shows.
pub const REPLAY_ON_CHANGE_EXAMPLE: &str = "bounded-14d";
/// The `replay_on_change` values the change-policy message lists, in its order.
pub const REPLAY_ON_CHANGE_VALID_VALUES: [&str; 3] = ["forward", "full", "bounded-<duration>"];
/// The code of the snapshot schema-change conflict with an enforced contract.
pub const CONTRACT_SCHEMA_CHANGE_CODE: &str = "K012";
/// The note naming the project setting that keeps microbatches sequential.
pub const MICROBATCH_CONCURRENCY_NOTE: &str = "the current value is [settings] \
microbatch_concurrency = false (from sqlbuild_project.toml or its default)";
/// The help showing the project setting that allows concurrent microbatches.
pub const MICROBATCH_CONCURRENCY_HELP: &str = "to run microbatches concurrently, set this in \
sqlbuild_project.toml:\n            [settings]\n            microbatch_concurrency = true";
/// The indent of the setting snippet lines in help text.
pub const SETTING_SNIPPET_INDENT: &str = "            ";
/// The duration-disabled cursor policy value.
pub const CURSOR_POLICY_DISABLED: &str = "disabled";
/// The zero-day cursor duration.
pub const ZERO_DAY_DURATION: &str = "0d";
/// The `batch_size` token that follows the cursor grain.
pub const EFFECTIVE_BATCH_SIZE: &str = "effective";
/// The SQL wildcard column.
pub const SQL_WILDCARD: &str = "*";
/// The `@@@name` placeholder sigil.
pub const PLACEHOLDER_SIGIL: &str = "@@@";

/// Keys that only incremental models may set.
pub const INCREMENTAL_ONLY_KEYS: [&str; 5] = [
    "on_schema_change",
    "replay_on_change",
    "append_cursor_inclusive",
    "merge_exclude_columns",
    "full_refresh",
];
/// Cursor input keys that require a cursor-based incremental model.
pub const CURSOR_INPUT_KEYS: [&str; 3] = [
    "cursor_inputs",
    "cursor_filter_inputs",
    "cursor_watermark_inputs",
];
/// Cursor input keys that have been removed in favour of `cursor_inputs`.
pub const REMOVED_CURSOR_INPUT_KEYS: [&str; 2] =
    ["cursor_filter_inputs", "cursor_watermark_inputs"];
/// Keys a snapshot model may not set.
pub const SNAPSHOT_DISALLOWED_KEYS: [&str; 16] = [
    "incremental_strategy",
    "incremental_mode",
    "append_cursor_inclusive",
    "batch_size",
    "cursor",
    "cursor_type",
    "cursor_grain",
    "cursor_inputs",
    "cursor_filter_inputs",
    "cursor_watermark_inputs",
    "cursor_end",
    "microbatch_strategy",
    "cursor_watermark_mode",
    "max_microbatches",
    "microbatch_limit",
    "lookback",
];
/// Keys a custom materialization may not set.
pub const CUSTOM_MATERIALIZATION_DISALLOWED_KEYS: [&str; 17] = [
    "on_schema_change",
    "incremental_strategy",
    "incremental_mode",
    "append_cursor_inclusive",
    "batch_size",
    "cursor",
    "cursor_type",
    "cursor_grain",
    "cursor_inputs",
    "cursor_filter_inputs",
    "cursor_watermark_inputs",
    "cursor_end",
    "microbatch_strategy",
    "cursor_watermark_mode",
    "max_microbatches",
    "microbatch_limit",
    "lookback",
];
/// The `microbatch_limit` keys, in no particular order.
pub const MICROBATCH_LIMIT_KEYS: [&str; 2] = ["max_batches", "action"];
/// The watermark `cursor_inputs` block keys, in no particular order.
pub const WATERMARK_BLOCK_KEYS: [&str; 2] = ["column", "roles"];
/// The config key naming the old-name compatibility view.
pub const OLD_NAME_VIEW_KEY: &str = "old_name_view";

/// `SqlReferenceKind` values a model may reference.
pub const REF_KIND: &str = "ref";
/// A seed reference.
pub const SEED_KIND: &str = "seed";
/// A source reference.
pub const SOURCE_KIND: &str = "source";
/// A scalar SQL function reference.
pub const UDF_KIND: &str = "udf";
/// A table function reference.
pub const TABLE_FUNCTION_KIND: &str = "table_fn";

/// The `inherit` storage policy value.
pub const INHERIT_POLICY: &str = "inherit";
/// The `disabled` retention value.
pub const DISABLED_RETENTION: &str = "disabled";
/// The permanent table type.
pub const PERMANENT_TABLE_TYPE: &str = "permanent";
/// The transient table type.
pub const TRANSIENT_TABLE_TYPE: &str = "transient";

/// The length of an ISO `YYYY-MM-DD` date.
pub const ISO_DATE_LENGTH: usize = 10;
/// Byte offsets of the separators in an ISO date.
pub const ISO_DATE_SEPARATOR_OFFSETS: [usize; 2] = [4, 7];
/// The length of a two-digit clock field.
pub const CLOCK_FIELD_LENGTH: usize = 2;
/// Clock part counts `HH:MM` and `HH:MM:SS`.
pub const CLOCK_PART_COUNTS: [usize; 2] = [2, 3];
/// The clock part count that may carry fractional seconds.
pub const CLOCK_PARTS_WITH_SECONDS: usize = 3;
/// The latest hour of a day.
pub const MAX_HOUR: i128 = 23;
/// The latest minute of an hour, and second of a minute.
pub const MAX_MINUTE: i128 = 59;
/// The length of a `HH:MM` UTC offset.
pub const UTC_OFFSET_LENGTH: usize = 5;
/// The first year Python's `datetime` represents.
pub const MIN_YEAR: i128 = 1;
/// The last year Python's `datetime` represents.
pub const MAX_YEAR: i128 = 9999;
/// Prefixes of the special values `Decimal` parses, after any sign.
pub const DECIMAL_SPECIAL_PREFIXES: [&str; 3] = ["inf", "nan", "snan"];
/// The last month whose civil-day computation shifts the year back.
pub const LAST_SHIFTED_MONTH: i128 = 2;
/// The position of days among duration units.
pub const DAY_UNIT_INDEX: usize = 2;
