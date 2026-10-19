//! SQLite store pragmas and maintenance budgets.

pub const BUSY_TIMEOUT_MS: u64 = 5_000;
/// `journal_size_limit`: the WAL is truncated to this size after checkpoints.
pub const JOURNAL_SIZE_LIMIT_BYTES: u64 = 64 * 1024 * 1024;
/// Maintenance runs at most once per this many seconds.
pub const MAINTENANCE_INTERVAL_SECONDS: u64 = 24 * 60 * 60;
/// Total time one maintenance run may spend deleting.
pub const MAINTENANCE_BUDGET_MS: u64 = 2_000;
/// Pages released by one `incremental_vacuum`.
pub const INCREMENTAL_VACUUM_PAGES: u32 = 2_048;
pub const META_MAINTENANCE_OVERDUE_KEY: &str = "overdue";
/// The selector naming the most recently started invocation.
pub const LAST_INVOCATION_SELECTOR: &str = "last";
