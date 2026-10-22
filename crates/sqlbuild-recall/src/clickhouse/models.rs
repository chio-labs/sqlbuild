//! A ClickHouse table's columns as written, stored rows found for a batch, and an insert plan.

use crate::records::models::RecallRow;
use crate::schema::models::Table;
use crate::store::models::InsertOutcome;

/// How one column is encoded in `RowBinary`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ColumnEncoding {
    String,
    Int64,
    Float64,
    UInt8,
    /// `DateTime64` with this many fractional digits.
    DateTime64(u64),
}

/// One column of a stored table: its name, encoding and whether it is `Nullable`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct StoredColumn {
    pub name: String,
    pub encoding: ColumnEncoding,
    pub nullable: bool,
}

/// What a batch's keys already hold in the store.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct StoredRow {
    /// The physical table name, such as `recall_events`.
    pub dataset: String,
    /// The key values joined by `:`, as conflicts record them.
    pub record_key: String,
    /// The content digest of the first copy ingested.
    pub first_hash: String,
    /// Every distinct content digest stored under the key.
    pub hashes: Vec<String>,
    /// Artifacts only: the newest `seen_at`, as Recall timestamp text.
    pub newest_seen_at: Option<String>,
}

/// The rows a batch still needs written, by table, and what the batch did.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct InsertPlan {
    pub inserts: Vec<(Table, Vec<RecallRow>)>,
    pub outcome: InsertOutcome,
}

/// One table whose TTL differs from the configured retention.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TtlMismatch {
    pub table: String,
    /// Days the stored TTL keeps rows, `None` when it has no day TTL.
    pub stored_days: Option<u64>,
    pub configured_days: u64,
}

/// The queries that read a store's state at setup.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct StoreStateSql {
    /// `name`, `is_view`, `create_table_query` of every Recall table and view present.
    pub relations: String,
    /// `table`, `name`, `type` of every column of the Recall tables, in table order.
    pub columns: String,
    /// The highest schema version recorded, 0 when none, and the age in seconds of the newest version row.
    pub schema_version: String,
    /// `table`, `name` of every column of the Recall views present.
    pub view_columns: String,
}
