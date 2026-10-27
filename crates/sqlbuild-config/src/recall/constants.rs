//! Recall setting keys and value vocabularies.

pub const RECALL_SECTION: &str = "recall";
/// Keys `[recall]` and `targets.<name>.recall` accept, sorted.
pub const RECALL_KEYS: [&str; 8] = [
    "audit_evidence",
    "diagnostics_min_severity",
    "enabled",
    "max_output_bytes",
    "read_connection",
    "retention",
    "shutdown_timeout",
    "write_connection",
];
/// The single store key `write_connection` and `read_connection` replaced.
pub const REMOVED_CONNECTION_KEY: &str = "connection";
/// The diagnostic severities a Recall store can keep from, least severe first.
pub const RECALL_SEVERITIES: [&str; 6] = ["trace", "debug", "info", "warning", "error", "critical"];
/// Which audit outcomes keep their evidence rows in Recall, the default first.
pub const AUDIT_EVIDENCE_MODES: [&str; 3] = ["warn-and-error", "error", "off"];
/// The longest shutdown flush budget, in milliseconds.
pub const MAX_SHUTDOWN_TIMEOUT_MS: u64 = 600_000;
/// The longest retention, in days.
pub const MAX_RETENTION_DAYS: u64 = 3_650;
pub(crate) const DECIMAL_RADIX: u32 = 10;
pub(crate) const HOURS_PER_DAY: u64 = 24;
pub(crate) const MILLIS_PER_SECOND: u64 = 1_000;
