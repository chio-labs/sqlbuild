//! Record vocabularies and limits.

/// The largest output chunk, in bytes.
pub const MAX_OUTPUT_CHUNK_BYTES: usize = 64 * 1024;
/// The output record ID infix, shared with command-output sink records.
pub const OUTPUT_RECORD_ID_INFIX: &str = "command-output";
pub const DIAGNOSTIC_RECORD_ID_INFIX: &str = "diagnostic";
/// Artifact digests are content digests with this prefix, as statement `sql_digest` without it.
pub const ARTIFACT_DIGEST_PREFIX: &str = "sha256:";
pub const SQL_ARTIFACT_KIND: &str = "sql";
pub const SQL_MEDIA_TYPE: &str = "text/x-sql";
pub const EXECUTED_SQL_ROLE: &str = "executed_sql";
/// Diagnostic severities, least severe first.
pub const SEVERITY_ORDER: [&str; 6] = ["trace", "debug", "info", "warning", "error", "critical"];
/// Event payload fields promoted to their own `recall_events` columns.
pub const PROMOTED_TEXT_FIELDS: [&str; 11] = [
    "command",
    "resource_kind",
    "resource_name",
    "error_code",
    "error_type",
    "query_id",
    "sql_digest",
    "intent",
    "statement_kind",
    "purpose",
    "outcome",
];
pub const PROMOTED_INTEGER_FIELDS: [&str; 3] = ["exit_code", "row_count", "affected_rows"];
pub const PROMOTED_REAL_FIELDS: [&str; 1] = ["duration_ms"];
pub const CORRELATION_FIELDS: [&str; 5] = [
    "run_id",
    "resource_id",
    "resource_attempt_id",
    "operation_id",
    "statement_id",
];
pub(crate) const MICROS_PER_SECOND: i64 = 1_000_000;
pub(crate) const SECONDS_PER_DAY: i64 = 86_400;
pub(crate) const DECIMAL_RADIX: u32 = 10;
pub(crate) const FEBRUARY: i64 = 2;
/// In a year counted from March, January is month index 10.
pub(crate) const MARCH_BASED_JANUARY_INDEX: i64 = 10;
/// The output column counting chunks dropped just before this one.
pub const DROPPED_BEFORE_COLUMN: &str = "dropped_before";
/// Initial capacity of the buffer a row's content hash is computed over.
pub(crate) const CONTENT_HASH_BUFFER_BYTES: usize = 1_024;
/// The output column holding the bytes a truncation gap replaces.
pub const OMITTED_BYTES_COLUMN: &str = "omitted_bytes";
/// The output column holding the sequences a truncation gap accounts for.
pub const OMITTED_SEQUENCES_COLUMN: &str = "omitted_sequences";
