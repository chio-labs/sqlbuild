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
