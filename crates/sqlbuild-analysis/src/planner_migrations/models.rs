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

/// One output expression and its alias binding facts.
#[derive(Debug)]
pub struct QueryProjection {
    pub name: String,
    pub expression: String,
    pub references: BTreeSet<String>,
    pub passthrough: bool,
}

/// A plain SELECT with canonical expressions and input binding facts.
#[derive(Debug)]
pub struct QueryShape {
    pub projections: Vec<QueryProjection>,
    pub body: String,
    pub alias_clauses: String,
    pub positional: bool,
    pub input_relations: Option<Vec<(String, String)>>,
    pub local_input_columns: BTreeSet<String>,
    pub clause_references: BTreeSet<String>,
}
