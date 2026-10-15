//! Columns of append-only state tables as their DDL declares them.

/// One declared column: its name, the adapter's rendered type and whether it is `NOT NULL`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TableColumn {
    pub name: String,
    pub rendered_type: String,
    pub required: bool,
}
