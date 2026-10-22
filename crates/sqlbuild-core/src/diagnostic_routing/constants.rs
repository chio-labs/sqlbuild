//! Diagnostic logging record names, fields and messages.

/// The root SQLBuild logger name.
pub const LOGGER_ROOT_NAME: &str = "sqlbuild";
/// The prefix of every SQLBuild child logger name.
pub const LOGGER_PREFIX: &str = "sqlbuild.";
/// The prefix of every SQLBuild structured record field.
pub const FIELD_PREFIX: &str = "sqlbuild_";
/// The record field holding a SQL statement's digest.
pub const SQL_DIGEST_FIELD: &str = "sqlbuild_sql_digest";
/// The record field holding SQL text.
pub const SQL_TEXT_FIELD: &str = "sqlbuild_sql";
/// The record field marking a trusted private SQL record.
pub const SQL_PRIVATE_RECORD_FIELD: &str = "sqlbuild_private_sql_record";
/// The message replacing every SQL record's text.
pub const REDACTED_SQL_LOG_MESSAGE: &str = "SQL diagnostic omitted";
/// The message of a record whose text cannot be formatted.
pub const UNFORMATTABLE_MESSAGE: &str = "<unformattable diagnostic message>";
/// The logger name of every retained SQL diagnostic.
pub const SQL_LOGGER_NAME: &str = "sqlbuild.sql";
/// The producer of retained diagnostics.
pub const DIAGNOSTIC_PRODUCER: &str = "sqlbuild";
/// The source of diagnostics retained from Python logging.
pub const DIAGNOSTIC_SOURCE: &str = "python_logging";
/// The retained field holding private SQL text.
pub const SQL_TEXT_DIAGNOSTIC_FIELD: &str = "sql_text";
/// Formatter-populated record fields never treated as structured extras.
pub const FORMATTER_RECORD_FIELDS: [&str; 2] = ["message", "asctime"];
/// The SQL digest field value prefix.
pub const SQL_DIGEST_PREFIX: &str = "sha256:";
/// The SQL action, intent and query ID record fields, in record order.
pub const SQL_ACTION_FIELD: &str = "sqlbuild_sql_action";
pub const SQL_INTENT_FIELD: &str = "sqlbuild_sql_intent";
pub const SQL_QUERY_ID_FIELD: &str = "sqlbuild_sql_query_id";
/// Execution identity fields, in diagnostic order.
pub const IDENTITY_FIELDS: [&str; 7] = [
    "invocation_id",
    "run_id",
    "resource_id",
    "resource_attempt_id",
    "operation_id",
    "statement_id",
    "log_stream_id",
];
/// The identity field defaulted to the handler's invocation.
pub const INVOCATION_ID_FIELD: &str = "invocation_id";
/// Structured fields a retained diagnostic may carry, in retention order.
pub const SAFE_FIELDS: [&str; 7] = [
    "sql_action",
    "sql_digest",
    "sql_intent",
    "sql_query_id",
    "channel",
    "subscriber",
    "error_type",
];
/// The safe fields a retained SQL diagnostic keeps.
pub const SQL_SAFE_FIELDS: [&str; 4] = ["sql_action", "sql_digest", "sql_intent", "sql_query_id"];
/// Python logging level numbers.
pub const LEVEL_INFO: i64 = 20;
pub const LEVEL_WARNING: i64 = 30;
pub const LEVEL_ERROR: i64 = 40;
pub const LEVEL_CRITICAL: i64 = 50;
/// Directories that hold installed packages, even inside a project (a project `.venv`).
pub const PACKAGE_DIRECTORIES: [&str; 2] = ["site-packages", "dist-packages"];
