//! Built-in Recall defaults.

/// The local store, relative to the project directory.
pub const DEFAULT_STORE_DIRECTORY: &str = "logs";
pub const DEFAULT_STORE_FILE_NAME: &str = "recall.sqlite3";
pub const DEFAULT_RETENTION_DAYS: u32 = 30;
pub const DEFAULT_SHUTDOWN_TIMEOUT_MS: u64 = 3_000;
pub const DEFAULT_DIAGNOSTICS_MIN_SEVERITY: &str = "info";
/// The connection key naming a connection's adapter; never passed to `connect()`.
pub const CONNECTION_ADAPTER_KEY: &str = "adapter";
pub const SQLITE_ADAPTER: &str = "sqlite";
pub const CLICKHOUSE_ADAPTER: &str = "clickhouse";
/// The ClickHouse connection option naming the database Recall's tables live in.
pub const CLICKHOUSE_DATABASE_KEY: &str = "database";
/// The database a ClickHouse connection uses when it names none.
pub const CLICKHOUSE_DEFAULT_DATABASE: &str = "default";
pub const SQLITE_PATH_KEY: &str = "path";
pub const PROJECT_FILE_NAME: &str = "sqlbuild_project.toml";
pub const LOCAL_FILE_NAME: &str = "sqlbuild_local.toml";
/// Bytes of each output stream the local SQLite store keeps per invocation: the first and last MiB.
pub const DEFAULT_SQLITE_MAX_OUTPUT_BYTES: u64 = 2 * 1024 * 1024;
