//! Relations, typed state values and column types of migration state events.

use sqlbuild_cursor::algebra::models::LocalDateTime;

/// A relation named by a migration event; only the name is required.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EventRelation {
    pub database: Option<String>,
    pub schema: Option<String>,
    pub name: String,
}

/// The declared physical type of a state event column.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StateColumnType {
    String,
    TextTimestamp,
}

/// One value of an event row as the caller holds it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum StateValue {
    Null,
    Text(String),
    /// A timestamp already normalized to UTC wall time.
    UtcTimestamp(LocalDateTime),
    /// Any other value, which no supported column type accepts.
    Other,
}

/// One column of an event row: its name, declared type and value.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct StateCell {
    pub column: String,
    pub column_type: StateColumnType,
    pub value: StateValue,
}

/// The order of an event in its history: UTC creation time, then event ID.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct EventOrder {
    pub created_at: LocalDateTime,
    pub event_id: String,
}

/// The fields of a recorded relation move that projections read.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MoveEventKey {
    pub order: EventOrder,
    pub origin: EventRelation,
    pub destination: EventRelation,
}

/// The fields of a recorded column rename that projections read.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ColumnEventKey {
    pub order: EventOrder,
    pub relation: EventRelation,
    pub origin_column: String,
    pub destination_column: String,
}

/// One step of an old-name view's lifecycle.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum OldNameStep {
    Required,
    OriginArchived,
    ViewCreated,
    ViewDropped,
}

/// The fields of one old-name fact that the history projection reads.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct OldNameFactKey {
    pub order: EventOrder,
    pub migration_event_id: String,
    pub step: OldNameStep,
}

/// One projected old-name history as indexes into the moves and facts it was built from.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct OldNameHistoryIndexes {
    pub moved: usize,
    pub required: usize,
    pub archived: Option<usize>,
    pub created: Option<usize>,
    pub dropped: Option<usize>,
}

/// The fields of a recorded column rename that the since-filter reads.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RecordedRenameKey {
    pub order: EventOrder,
    pub relation: EventRelation,
    pub records_event: bool,
}

/// The order of a stored fingerprint: its ISO timestamp text, then its run ID.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct FingerprintOrder {
    pub timestamp: String,
    pub run_id: String,
}

/// The fields of a stored model fingerprint that the newest-fingerprint lookup reads.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FingerprintKey {
    pub order: FingerprintOrder,
    pub node_name: String,
    pub target: Option<EventRelation>,
}
