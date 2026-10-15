//! Execution history limits, lifecycle facts and the SQL each backend stores them with.

pub const DEFAULT_PAGE_LIMIT: i64 = 100;
pub const MAX_PAGE_LIMIT: i64 = 1000;
pub const SCHEMA_VERSION: i64 = 1;
pub const RUN_STARTED_EVENT_TYPE: &str = "run_started";
pub const RUN_COMPLETED_EVENT_TYPE: &str = "run_completed";
pub const RUN_FAILED_EVENT_TYPE: &str = "run_failed";
pub const RUN_CURSOR_PART_COUNT: usize = 3;
pub const SQLITE_EVENT_CURSOR_PREFIX: &str = "sqlite-event:";
pub const SQLITE_RUN_CURSOR_PREFIX: &str = "sqlite-run:";
pub const POSTGRES_EVENT_CURSOR_PREFIX: &str = "postgres-event:";
pub const POSTGRES_RUN_CURSOR_PREFIX: &str = "postgres-run:";
pub const SQLITE_BUSY_TIMEOUT_MS: i64 = 5_000;
pub const POSTGRES_CONNECT_TIMEOUT_SECONDS: i64 = 10;
pub const POSTGRES_STATEMENT_TIMEOUT_MS: i64 = 30_000;
pub const POSTGRES_TRANSACTION_RETRIES: i64 = 3;
pub const POSTGRES_MAX_CONNECT_TIMEOUT_SECONDS: i64 = 300;
pub const POSTGRES_MAX_STATEMENT_TIMEOUT_MS: i64 = 3_600_000;
pub const POSTGRES_MAX_TRANSACTION_RETRIES: i64 = 10;
pub const POSTGRES_MIGRATION_LOCK_ID: i64 = 7_218_786_101;
pub const POSTGRES_HISTORY_LOCK_ID: i64 = 7_218_786_102;
pub const POSTGRES_RETRYABLE_SQLSTATES: [&str; 2] = ["40001", "40P01"];
/// Text envelope fields stored next to each event, in `EventEnvelope::text_fields` order.
pub const ENVELOPE_TEXT_FIELDS: [&str; 9] = [
    "producer",
    "producer_version",
    "event_type",
    "invocation_id",
    "run_id",
    "resource_id",
    "resource_attempt_id",
    "operation_id",
    "statement_id",
];
pub const SQLITE_SCHEMA: [&str; 8] = [
    "CREATE TABLE IF NOT EXISTS execution_history_metadata (\n    key TEXT PRIMARY KEY,\n    value TEXT NOT NULL\n)",
    "CREATE TABLE IF NOT EXISTS lifecycle_event_log (\n    storage_id INTEGER PRIMARY KEY AUTOINCREMENT,\n    event_id TEXT NOT NULL UNIQUE,\n    schema_version INTEGER NOT NULL,\n    producer TEXT,\n    event_type TEXT,\n    occurred_at TEXT,\n    received_at TEXT NOT NULL,\n    invocation_id TEXT,\n    run_id TEXT,\n    resource_id TEXT,\n    resource_attempt_id TEXT,\n    operation_id TEXT,\n    statement_id TEXT,\n    payload_json TEXT NOT NULL,\n    content_digest TEXT NOT NULL\n)",
    "CREATE INDEX IF NOT EXISTS lifecycle_event_log_run_storage\n    ON lifecycle_event_log (run_id, storage_id)",
    "CREATE INDEX IF NOT EXISTS lifecycle_event_log_invocation_storage\n    ON lifecycle_event_log (invocation_id, storage_id)",
    "CREATE INDEX IF NOT EXISTS lifecycle_event_log_type_storage\n    ON lifecycle_event_log (event_type, storage_id)",
    "CREATE TABLE IF NOT EXISTS run_projection (\n    run_id TEXT PRIMARY KEY,\n    invocation_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n    status TEXT NOT NULL,\n    is_complete INTEGER NOT NULL,\n    last_event_cursor TEXT NOT NULL,\n    last_storage_order INTEGER NOT NULL,\n    command TEXT,\n    target TEXT,\n    environment TEXT,\n    started_at TEXT,\n    ended_at TEXT,\n    projection_schema_version INTEGER NOT NULL\n)",
    "CREATE INDEX IF NOT EXISTS run_projection_created ON run_projection (created_at, run_id)",
    "CREATE INDEX IF NOT EXISTS run_projection_invocation_created\n    ON run_projection (invocation_id, created_at, run_id)",
];
pub const POSTGRES_SCHEMA: [&str; 8] = [
    "CREATE TABLE IF NOT EXISTS sqlbuild_storage_migrations (\n        singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),\n        schema_version INTEGER NOT NULL,\n        storage_namespace TEXT NOT NULL,\n        migrated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP\n    )",
    "CREATE TABLE IF NOT EXISTS sqlbuild_lifecycle_event_log (\n        storage_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,\n        event_id TEXT NOT NULL UNIQUE,\n        schema_version INTEGER NOT NULL,\n        producer TEXT,\n        producer_version TEXT,\n        event_type TEXT,\n        occurred_at TIMESTAMPTZ,\n        received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,\n        invocation_id TEXT,\n        run_id TEXT,\n        resource_id TEXT,\n        resource_attempt_id TEXT,\n        operation_id TEXT,\n        statement_id TEXT,\n        payload_json TEXT NOT NULL,\n        content_digest TEXT NOT NULL\n    )",
    "CREATE INDEX IF NOT EXISTS sqlbuild_lifecycle_event_log_run_storage\n    ON sqlbuild_lifecycle_event_log (run_id, storage_id)",
    "CREATE INDEX IF NOT EXISTS sqlbuild_lifecycle_event_log_invocation_storage\n    ON sqlbuild_lifecycle_event_log (invocation_id, storage_id)",
    "CREATE INDEX IF NOT EXISTS sqlbuild_lifecycle_event_log_type_storage\n    ON sqlbuild_lifecycle_event_log (event_type, storage_id)",
    "CREATE TABLE IF NOT EXISTS sqlbuild_run_projection (\n        run_id TEXT PRIMARY KEY,\n        invocation_id TEXT NOT NULL,\n        created_at TIMESTAMPTZ NOT NULL,\n        status TEXT NOT NULL,\n        is_complete BOOLEAN NOT NULL,\n        last_event_cursor TEXT NOT NULL,\n        last_event_storage_id BIGINT NOT NULL,\n        command TEXT,\n        target TEXT,\n        environment TEXT,\n        started_at TIMESTAMPTZ,\n        ended_at TIMESTAMPTZ,\n        projection_schema_version INTEGER NOT NULL\n    )",
    "CREATE INDEX IF NOT EXISTS sqlbuild_run_projection_created\n    ON sqlbuild_run_projection (created_at, run_id)",
    "CREATE INDEX IF NOT EXISTS sqlbuild_run_projection_invocation_created\n    ON sqlbuild_run_projection (invocation_id, created_at, run_id)",
];
pub const SQLITE_EVENT_INSERT: &str = "INSERT INTO lifecycle_event_log (\n                    event_id, schema_version, producer, event_type, occurred_at, received_at,\n                    invocation_id, run_id, resource_id, resource_attempt_id, operation_id,\n                    statement_id, payload_json, content_digest\n                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)";
pub const POSTGRES_EVENT_INSERT: &str = "INSERT INTO sqlbuild_lifecycle_event_log (\n                    event_id, schema_version, producer, producer_version, event_type, occurred_at,\n                    invocation_id, run_id, resource_id, resource_attempt_id, operation_id,\n                    statement_id, payload_json, content_digest\n                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)\n                ON CONFLICT (event_id) DO NOTHING RETURNING *";
pub const SQLITE_RUN_INSERT: &str = "INSERT INTO run_projection (\n                run_id, invocation_id, created_at, status, is_complete, last_event_cursor,\n                last_storage_order, command, target, environment, started_at, ended_at,\n                projection_schema_version\n            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)";
pub const POSTGRES_RUN_INSERT: &str = "INSERT INTO sqlbuild_run_projection (\n                    run_id, invocation_id, created_at, status, is_complete, last_event_cursor,\n                    last_event_storage_id, command, target, environment, started_at, ended_at,\n                    projection_schema_version\n                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)";
pub const MEMORY_PATH: &str = ":memory:";
pub const SQLITE_DIRECTORY_NAME: &str = ".sqlbuild";
pub const SQLITE_FILE_NAME: &str = "history.sqlite3";
pub const SQLITE_DIRECTORY_MODE: u32 = 0o700;
pub const SQLITE_FILE_MODE: u32 = 0o600;
pub const SQLITE_HEALTHY_CHECK_RESULT: &str = "ok";
pub const SQLITE_METADATA_TABLE: &str = "execution_history_metadata";
pub const SQLITE_NAMESPACE_KEY: &str = "storage_namespace";
pub const SQLITE_SCHEMA_VERSION_KEY: &str = "schema_version";
pub const SQLITE_FOREIGN_KEYS: &str = "PRAGMA foreign_keys = ON";
pub const SQLITE_JOURNAL_MODE: &str = "PRAGMA journal_mode = WAL";
pub const SQLITE_QUICK_CHECK: &str = "PRAGMA quick_check";
pub const SQLITE_BEGIN: &str = "BEGIN IMMEDIATE";
pub const SQLITE_COMMIT: &str = "COMMIT";
pub const SQLITE_ROLLBACK: &str = "ROLLBACK";
pub const SQLITE_INSERT_NAMESPACE: &str =
    "INSERT OR IGNORE INTO execution_history_metadata(key, value) VALUES (?, ?)";
pub const SQLITE_INSERT_SCHEMA_VERSION: &str =
    "INSERT OR REPLACE INTO execution_history_metadata(key, value) VALUES (?, ?)";
pub const SQLITE_METADATA_EXISTS: &str =
    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?";
pub const SQLITE_METADATA_VALUE: &str =
    "SELECT value FROM execution_history_metadata WHERE key = ?";
pub const SQLITE_EVENT_BY_ID: &str = "SELECT * FROM lifecycle_event_log WHERE event_id = ?";
pub const SQLITE_EVENT_BY_STORAGE_ID: &str =
    "SELECT * FROM lifecycle_event_log WHERE storage_id = ?";
pub const SQLITE_EVENT_EXISTS: &str = "SELECT 1 FROM lifecycle_event_log WHERE storage_id = ?";
pub const SQLITE_ALL_EVENTS: &str = "SELECT * FROM lifecycle_event_log ORDER BY storage_id";
pub const SQLITE_ALL_RUNS: &str = "SELECT * FROM run_projection ORDER BY created_at, run_id";
pub const SQLITE_RUN_BY_ID: &str = "SELECT * FROM run_projection WHERE run_id = ?";
pub const SQLITE_RUN_EXISTS: &str =
    "SELECT 1 FROM run_projection WHERE created_at = ? AND run_id = ?";
pub const SQLITE_DELETE_RUNS: &str = "DELETE FROM run_projection";
pub const POSTGRES_SESSION_TIMEOUT: &str = "SELECT set_config('statement_timeout', %s, false)";
pub const POSTGRES_TRANSACTION_TIMEOUT: &str = "SELECT set_config('statement_timeout', %s, true)";
pub const POSTGRES_ADVISORY_LOCK: &str = "SELECT pg_advisory_xact_lock(%s)";
pub const POSTGRES_MIGRATIONS_EXIST: &str =
    "SELECT to_regclass('sqlbuild_storage_migrations') AS table_name";
pub const POSTGRES_SCHEMA_VERSION: &str =
    "SELECT schema_version FROM sqlbuild_storage_migrations WHERE singleton = TRUE";
pub const POSTGRES_NAMESPACE: &str =
    "SELECT storage_namespace FROM sqlbuild_storage_migrations WHERE singleton = TRUE";
pub const POSTGRES_RECORD_MIGRATION: &str = "INSERT INTO sqlbuild_storage_migrations\n                (singleton, schema_version, storage_namespace)\n                VALUES (TRUE, %s, %s)\n                ON CONFLICT (singleton) DO UPDATE SET\n                    schema_version = EXCLUDED.schema_version,\n                    migrated_at = CURRENT_TIMESTAMP";
pub const POSTGRES_EVENT_BY_ID: &str =
    "SELECT * FROM sqlbuild_lifecycle_event_log WHERE event_id = %s";
pub const POSTGRES_EVENT_EXISTS: &str =
    "SELECT 1 AS present FROM sqlbuild_lifecycle_event_log WHERE storage_id = %s";
pub const POSTGRES_ALL_EVENTS: &str =
    "SELECT * FROM sqlbuild_lifecycle_event_log ORDER BY storage_id";
pub const POSTGRES_ALL_RUNS: &str =
    "SELECT * FROM sqlbuild_run_projection ORDER BY created_at, run_id";
pub const POSTGRES_RUN_BY_ID: &str = "SELECT * FROM sqlbuild_run_projection WHERE run_id = %s";
pub const POSTGRES_RUN_EXISTS: &str =
    "SELECT 1 AS present FROM sqlbuild_run_projection WHERE created_at = %s AND run_id = %s";
pub const POSTGRES_DELETE_RUNS: &str = "DELETE FROM sqlbuild_run_projection";
pub const POSTGRES_PING: &str = "SELECT 1";
pub const SQLITE_PLACEHOLDER: &str = "?";
pub const POSTGRES_PLACEHOLDER: &str = "%s";
pub const SQLITE_EVENT_TABLE: &str = "lifecycle_event_log";
pub const POSTGRES_EVENT_TABLE: &str = "sqlbuild_lifecycle_event_log";
pub const SQLITE_RUN_TABLE: &str = "run_projection";
pub const POSTGRES_RUN_TABLE: &str = "sqlbuild_run_projection";
pub const CURSOR_SEPARATOR: char = ':';
pub const MALFORMED_EVENT_CURSOR: &str = "event cursor is malformed or belongs to another backend";
pub const FOREIGN_EVENT_CURSOR: &str = "event cursor is not valid for this storage";
pub const UNKNOWN_EVENT_CURSOR: &str = "event cursor does not identify a durable event";
pub const MALFORMED_RUN_CURSOR: &str = "run cursor is malformed or belongs to another backend";
pub const RUN_CURSOR_TIMESTAMP: &str = "run cursor contains an invalid timestamp";
pub const UNKNOWN_RUN_CURSOR: &str = "run cursor does not identify a run in this storage";
pub const MISSING_EVENT_ID: &str = "canonical lifecycle event requires a non-empty string event_id";
pub const UTC_OFFSET_TEXT: &str = "+00:00";
pub const FIRST_POSITION: i64 = 1;
pub const NO_SCHEMA: i64 = 0;
pub const MIN_TIMEOUT: i64 = 1;
pub const MIN_RETRIES: i64 = 0;
pub const MIN_PAGE_LIMIT: i64 = 1;
pub const DUPLICATE_ORDER: &str = "storage_order must uniquely identify a durable event";
