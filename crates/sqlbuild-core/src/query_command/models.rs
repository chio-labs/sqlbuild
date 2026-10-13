//! A query result as its text formats display it.

/// Column names, each row's cells as display text, and whether the limit cut rows off.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct QueryDisplay {
    pub columns: Vec<String>,
    pub rows: Vec<Vec<String>>,
    pub truncated: bool,
    pub limit: Option<i64>,
}
