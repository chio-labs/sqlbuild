//! Recall setting keys and value vocabularies.

pub const RECALL_SECTION: &str = "recall";
/// Keys `[recall]` and `targets.<name>.recall` accept, sorted.
pub const RECALL_KEYS: [&str; 6] = [
    "connection",
    "diagnostics_min_severity",
    "enabled",
    "max_output_bytes",
    "retention",
    "shutdown_timeout",
];
/// The diagnostic severities a Recall store can keep from, least severe first.
pub const RECALL_SEVERITIES: [&str; 6] = ["trace", "debug", "info", "warning", "error", "critical"];
/// The longest shutdown flush budget, in milliseconds.
pub const MAX_SHUTDOWN_TIMEOUT_MS: u64 = 600_000;
/// The longest retention, in days.
pub const MAX_RETENTION_DAYS: u64 = 3_650;
pub(crate) const DECIMAL_RADIX: u32 = 10;
pub(crate) const HOURS_PER_DAY: u64 = 24;
pub(crate) const MILLIS_PER_SECOND: u64 = 1_000;
