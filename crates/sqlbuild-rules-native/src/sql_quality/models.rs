use std::collections::{HashMap, HashSet};

use polyglot_sql::Expression;
use polyglot_sql::tokens::Token;

/// Inputs for one body's quality Rules, borrowed from the native lint request.
#[derive(Debug)]
pub(crate) struct QualityRequest<'a> {
    pub(crate) statements: &'a [Expression],
    pub(crate) tokens: &'a [Token],
    pub(crate) enabled: &'a HashSet<String>,
    pub(crate) max_literal_length: usize,
    pub(crate) max_ranking_order_by: usize,
    pub(crate) relation_keys: &'a HashMap<String, Vec<Vec<String>>>,
    pub(crate) externally_referenced_ctes: &'a HashSet<String>,
    pub(crate) fixture_body: bool,
}
