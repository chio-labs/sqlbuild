//! Materialization, action and cursor vocabulary the plan display reads.

pub(crate) const VIEW: &str = "view";
pub(crate) const TABLE: &str = "table";
pub(crate) const INCREMENTAL: &str = "incremental";
pub(crate) const SNAPSHOT: &str = "snapshot";
pub(crate) const CUSTOM: &str = "custom";
pub(crate) const MICROBATCH_MODE: &str = "microbatch";
pub(crate) const INCREMENTAL_ACTIONS: [&str; 3] = [
    "incremental_append",
    "incremental_delete_insert",
    "incremental_merge",
];
pub const INTEGER_CURSOR: &str = "integer";
pub const TIMESTAMP_CURSOR: &str = "timestamp";
pub const DEFAULT_CURSOR_GRAIN: &str = "second";
pub(crate) const WHOLE_DAY_CURSOR_GRAINS: [&str; 3] = ["day", "month", "year"];
pub(crate) const EFFECTIVE_BATCH_SIZE_TOKEN: &str = "effective";
pub(crate) const GRAIN_BATCH_SIZE: [(&str, &str); 6] = [
    ("second", "1s"),
    ("minute", "1m"),
    ("hour", "1h"),
    ("day", "1d"),
    ("month", "1mo"),
    ("year", "1y"),
];
