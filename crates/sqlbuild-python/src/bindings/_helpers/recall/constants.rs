//! Recall binding names, environment variables and error codes.

/// Seconds between heartbeats; tests shorten it to observe abandoned invocations quickly.
pub(crate) const HEARTBEAT_ENVIRONMENT: &str = "SQLBUILD_RECALL_HEARTBEAT_SECONDS";
/// Marker files under `target/` limiting store notices to one per interval.
pub(crate) const DDL_NOTICE_PREFIX: &str = ".recall-notice-";
pub(crate) const NOTICE_INTERVAL_SECONDS: u64 = 24 * 60 * 60;
/// Hex digits of the hostname digest recorded as the host token.
pub(crate) const HOST_TOKEN_LENGTH: usize = 16;
/// The shortest heartbeat interval the test environment variable may request.
pub(crate) const MINIMUM_HEARTBEAT_SECONDS: f64 = 0.01;
/// The compute-log stream index of stdout; every other output index is stderr.
pub(crate) const STDOUT_STREAM_INDEX: usize = 0;
pub(crate) const RECALL_DISABLED_CODE: &str = "C970";
pub(crate) const RECALL_STORE_CODE: &str = "C971";
pub(crate) const RECALL_NOT_FOUND_CODE: &str = "C972";
pub(crate) const RECALL_AMBIGUOUS_CODE: &str = "C973";
pub(crate) const RECALL_QUERY_CODE: &str = "C974";
pub(crate) const RECALL_SETTINGS_CODE: &str = "C975";
pub(crate) const WAREHOUSE_BACKEND: &str = "warehouse";
/// Default cell width in text formats, in bytes.
pub(crate) const DEFAULT_MAX_CELL_BYTES: usize = 4096;
pub(crate) const LONG_FORMAT: &str = "long";
pub(crate) const TABLE_FORMAT: &str = "table";
pub(crate) const CSV_FORMAT: &str = "csv";
pub(crate) const JSON_FORMAT: &str = "json";
/// The standard base64 alphabet binary JSON cells are encoded with.
pub(crate) const BASE64_ALPHABET: &[u8; 64] =
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
/// Join keys `sqb recall schema` points out.
pub(crate) const JOIN_KEYS: [&str; 5] = [
    "invocation_id",
    "statement_id",
    "sql_digest",
    "run_id",
    "resource_id",
];
/// Rows `sqb recall query` returns without `--limit` or `--no-limit`.
pub(crate) const DEFAULT_QUERY_LIMIT: i64 = 100;
/// The invocation selector naming the most recently started invocation.
pub(crate) const LAST_INVOCATION: &str = "last";
/// The keyword arguments the `sqb recall` dispatch route passes.
pub(crate) const RECALL_OPTIONS: [&str; 13] = [
    "project_dir",
    "selected_target",
    "recall_command",
    "sql",
    "backend",
    "output_format",
    "limit",
    "no_limit",
    "max_cell_bytes",
    "relation",
    "invocation",
    "stream",
    "tail",
];
