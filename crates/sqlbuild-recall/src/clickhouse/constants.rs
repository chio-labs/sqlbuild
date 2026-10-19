//! ClickHouse store batching, error codes, encoding and SQL markers.

use crate::schema::models::Table;

/// Rows one insert batch takes; ClickHouse prefers few large inserts to many small ones.
pub const BATCH_ROWS: usize = 5_000;
/// Longest wait for a batch to fill, so each table gets at most about one part per second per writer.
pub const BATCH_WINDOW_MS: u64 = 1_000;
/// Server error codes meaning the user may not create or write the store.
pub const PERMISSION_CODES: [u64; 4] = [
    164, // READONLY
    291, // DATABASE_ACCESS_DENIED
    497, // ACCESS_DENIED
    516, // AUTHENTICATION_FAILED
];
/// Server error codes worth retrying with the same rows and deduplication tokens.
pub const TRANSIENT_CODES: [u64; 9] = [
    159, // TIMEOUT_EXCEEDED
    202, // TOO_MANY_SIMULTANEOUS_QUERIES
    209, // SOCKET_TIMEOUT
    210, // NETWORK_ERROR
    241, // MEMORY_LIMIT_EXCEEDED
    242, // TABLE_IS_READ_ONLY
    252, // TOO_MANY_PARTS
    319, // UNKNOWN_STATUS_OF_INSERT
    425, // SYSTEM_ERROR
];
/// UNKNOWN_DATABASE: Recall never creates databases.
pub const UNKNOWN_DATABASE_CODE: u64 = 81;
/// Where a client error message states the server code.
pub(crate) const SERVER_CODE_MARKERS: [&str; 2] = ["Code: ", "code: "];
/// The most fractional digits a `DateTime64` holds.
pub(crate) const MAX_DATETIME64_PRECISION: u64 = 9;
/// The fractional digits of Recall timestamps.
pub(crate) const MICROS_DIGITS: u64 = 6;
/// One decimal digit of timestamp scale.
pub(crate) const DECIMAL_SCALE: i64 = 10;
/// The column the store sets when a row is written.
pub(crate) const INGESTED_AT_COLUMN: &str = "ingested_at";
pub(crate) const VARINT_PAYLOAD_BITS: u32 = 7;
pub(crate) const VARINT_CONTINUE: u8 = 0x80;
pub(crate) const VARINT_MASK: u64 = 0x7f;
pub(crate) const DECIMAL_RADIX: u32 = 10;
/// Tables written without a lookup: unique by construction, or evidence themselves.
pub(crate) const UNCHECKED_TABLES: [Table; 2] = [Table::Meta, Table::Conflicts];
/// `formatDateTime` pattern of Recall timestamp text.
pub(crate) const TIMESTAMP_PATTERN: &str = "%Y-%m-%dT%H:%i:%S.%fZ";
/// Where a `CREATE TABLE` query states its TTL, the clause after it, and the day interval in it.
pub(crate) const TTL_MARKER: &str = " TTL ";
pub(crate) const SETTINGS_MARKER: &str = " SETTINGS ";
pub(crate) const DAY_INTERVAL: &str = "toIntervalDay(";
