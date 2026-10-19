//! The physical shape of Recall tables and the options their DDL is rendered with.

/// The SQL dialect a Recall store speaks.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Dialect {
    Sqlite,
    ClickHouse,
}

/// The logical type of one Recall column.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ColumnType {
    Text,
    Integer,
    Real,
    Blob,
    /// ISO-8601 UTC text with microseconds in SQLite, `DateTime64(6, 'UTC')` in ClickHouse.
    Timestamp,
    /// JSON text.
    Json,
    /// 0 or 1.
    Boolean,
}

/// One column: its name, type and whether it may be null.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ColumnSpec {
    pub name: &'static str,
    pub column_type: ColumnType,
    pub nullable: bool,
}

impl ColumnSpec {
    /// A column that is never null.
    #[must_use]
    pub const fn required(name: &'static str, column_type: ColumnType) -> Self {
        Self {
            name,
            column_type,
            nullable: false,
        }
    }

    /// A column that may be null.
    #[must_use]
    pub const fn optional(name: &'static str, column_type: ColumnType) -> Self {
        Self {
            name,
            column_type,
            nullable: true,
        }
    }
}

/// One Recall table.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TableSpec {
    pub name: &'static str,
    /// Columns specific to this table; every table also has the common columns.
    pub columns: &'static [ColumnSpec],
    /// The deterministic identity of a row; a second row with this key is a duplicate.
    pub key: &'static [&'static str],
    /// SQLite secondary indexes: name suffix and columns.
    pub sqlite_indexes: &'static [(&'static str, &'static [&'static str])],
    /// ClickHouse engine without arguments: `ReplacingMergeTree` or `MergeTree`.
    pub clickhouse_engine: &'static str,
    /// ClickHouse `ORDER BY` columns.
    pub clickhouse_order_by: &'static [&'static str],
    /// Days ClickHouse keeps rows beyond retention; artifacts outlive their references.
    pub ttl_extra_days: u32,
    /// The `ReplacingMergeTree` version column: the newest copy survives merges.
    pub clickhouse_version: Option<&'static str>,
    /// The timestamp column partitions and TTL derive from.
    pub expiry_column: &'static str,
}

/// The tables Recall writes.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Table {
    Invocations,
    Output,
    Events,
    Diagnostics,
    Artifacts,
    ArtifactRefs,
    Heartbeats,
    Delivery,
    Meta,
    Conflicts,
}

/// What DDL is rendered with: database (ClickHouse), retention and cluster.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DdlOptions {
    pub database: Option<String>,
    pub retention_days: u32,
    pub cluster: Option<String>,
}

/// The statements SQLite maintenance runs, with their positional parameters.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SqliteRetentionSql {
    /// `?1` cutoff, `?2` now, `?3` limit: expired invocation IDs that are not running.
    pub expired_invocations: String,
    /// Per table, `?1` a JSON array of invocation IDs to delete.
    pub delete_invocations: Vec<(Table, String)>,
    /// `?1` cutoff: artifacts no remaining reference names.
    pub delete_orphan_artifacts: String,
    /// `?1` cutoff: maintenance claims older than retention.
    pub delete_old_claims: String,
}
