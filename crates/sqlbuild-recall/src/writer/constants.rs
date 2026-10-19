//! Queue bounds, batching and timing of the Recall writer.

pub const QUEUE_RECORD_CAPACITY: usize = 10_000;
pub const QUEUE_BYTE_CAPACITY: usize = 32 * 1024 * 1024;
pub const BATCH_ROWS: usize = 500;
pub const BATCH_WINDOW_MS: u64 = 250;
/// Contiguous writes to one stream coalesce into one chunk for at most this long.
pub const OUTPUT_COALESCE_MS: u64 = 250;
pub const DEFAULT_HEARTBEAT_INTERVAL_MS: u64 = 30_000;
/// An invocation is abandoned once its last heartbeat is this many intervals old.
pub const HEARTBEAT_STALE_INTERVALS: u32 = 3;
/// Table setup may delay the command by at most this long.
pub const SETUP_BUDGET_MS: u64 = 2_000;
/// Longest single backoff between retries of a busy write.
pub const MAX_RETRY_BACKOFF_MS: u64 = 500;
/// A batch that stays busy this long while the command runs is counted as failed.
pub const RUNNING_RETRY_LIMIT_MS: u64 = 30_000;
