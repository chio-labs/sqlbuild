//! A query result as its text formats display it.

/// Column names and types, each row's cells as display text, and whether the limit cut rows off.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct QueryDisplay {
    pub columns: Vec<String>,
    /// Each column's type as the warehouse names it, where known; empty when no type is known.
    pub types: Vec<Option<String>>,
    /// Columns whose values are numbers, right-aligned in the box layout.
    pub numeric: Vec<bool>,
    pub rows: Vec<Vec<String>>,
    pub truncated: bool,
    pub limit: Option<i64>,
}

/// How a result is laid out as text.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum QueryLayout {
    /// A box when every row fits `width` terminal cells, else one record per row.
    Fitted { width: usize },
    /// One record per row.
    Long,
}
