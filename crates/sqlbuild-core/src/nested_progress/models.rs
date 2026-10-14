//! Plain data of grouped command progress rows.

use crate::build_progress::models::ErrorText;

/// One nested child row drawn under a completed item.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct NestedChildRow {
    pub label: String,
    pub name: String,
    pub status_text: String,
    pub detail: String,
}

/// One completed item with its child rows and error.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct NestedItem {
    pub item_name: String,
    pub status_text: String,
    pub detail: String,
    pub error: ErrorText,
    pub child_rows: Vec<NestedChildRow>,
}

/// The row label, name column width and terminal width of one command's rows.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct NestedLayout {
    pub label: String,
    pub name_width: usize,
    pub columns: usize,
}

/// Aggregate worker state of concurrently running audits.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct AuditAggregate {
    pub running: usize,
    pub completed: usize,
    pub total: usize,
    pub workers: i64,
}
