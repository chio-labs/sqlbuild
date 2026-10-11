use std::collections::{HashMap, HashSet};

use polyglot_sql::tokens::Token;
use polyglot_sql::{DialectType, Expression};

/// Inputs for one body's quality Rules, borrowed from the native lint request.
#[derive(Debug)]
pub(crate) struct QualityRequest<'a> {
    pub(crate) statements: &'a [Expression],
    pub(crate) tokens: &'a [Token],
    pub(crate) dialect: DialectType,
    pub(crate) enabled: &'a HashSet<String>,
    pub(crate) max_literal_length: usize,
    pub(crate) max_ranking_order_by: usize,
    pub(crate) relation_keys: &'a HashMap<String, Vec<Vec<String>>>,
    pub(crate) externally_referenced_ctes: &'a HashSet<String>,
    pub(crate) fixture_body: bool,
}

/// One project relation's declared key facts: its incremental config and audited columns.
#[derive(Debug, Clone, Default)]
pub struct DeclaredRelation {
    /// `ref`, `seed` or `source`.
    pub kind: String,
    pub name: String,
    pub materialized: String,
    pub incremental_mode: String,
    pub incremental_strategy: String,
    pub has_cursor: bool,
    /// The configured `unique_key` columns, when it is a name or a list of names.
    pub unique_key: Option<Vec<String>>,
    pub columns: Vec<DeclaredKeyColumn>,
    /// Table-level audits as `(definition name, its string column argument)`.
    pub audits: Vec<(String, Option<String>)>,
}

/// One declared column: its name, its audit definition names and whether it is declared non-null.
#[derive(Debug, Clone, Default)]
pub struct DeclaredKeyColumn {
    pub name: String,
    pub audits: Vec<String>,
    pub not_nullable: bool,
}
