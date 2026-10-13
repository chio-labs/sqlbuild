//! Cost command selectors, sort fields and defaults.

pub const HISTORY_SELECTOR: &str = "history";
pub const LATEST_SELECTOR: &str = "latest";
pub const DESCENDING_ORDER: &str = "desc";
pub const DEFAULT_HISTORY_SORT: &str = "completed";
pub const DEFAULT_DETAIL_SORT: &str = "cost";
pub const DEFAULT_HISTORY_LIMIT: i64 = 10;
pub const ISO_DATE_LENGTH: usize = 10;
/// History sort fields, sorted.
pub const HISTORY_SORT_FIELDS: [&str; 6] = [
    "completed",
    "cost",
    "credits",
    "duration",
    "models",
    "status",
];
/// Breakdown sort fields, sorted.
pub const BREAKDOWN_SORT_FIELDS: [&str; 6] =
    ["busy", "cost", "credits", "model", "scanned", "warehouse"];
/// History fields whose runs without metrics sort after the rest.
pub const HISTORY_METRIC_SORT_FIELDS: [&str; 2] = ["cost", "credits"];
/// Statuses whose runs carry no complete metrics.
pub const MISSING_METRIC_STATUSES: [&str; 4] =
    ["pending", "partial", "unavailable", "collection_failed"];
/// Statuses a delayed refresh may still improve.
pub const REFRESHABLE_STATUSES: [&str; 2] = ["pending", "partial"];
pub const LEDGER_PERSISTENCE_FAILURE_PREFIX: &str = "Statement-ledger persistence failed (";
