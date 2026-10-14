//! Data used to match output columns across a migration.

use std::collections::BTreeSet;

/// A named projection with canonical expression and reference names.
#[derive(Debug)]
pub struct Projection {
    pub name: String,
    pub key: String,
    pub expression: String,
    pub references: BTreeSet<String>,
}

/// A suggestion to declare an explicit column migration.
#[derive(Debug)]
pub struct RenameHint {
    pub added_column: String,
    pub candidate_columns: Vec<String>,
    pub identical: bool,
}
