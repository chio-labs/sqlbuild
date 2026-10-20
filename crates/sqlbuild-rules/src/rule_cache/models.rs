//! SQL rule cache key inputs, stored entries and lookups.

/// Everything besides SQL text that changes SQL rule findings.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LintKeyInput {
    pub dialect: String,
    pub max_literal_length: i64,
    pub max_ranking_order_by: i64,
    /// Each relation and its key column sets, in any order.
    pub relation_keys: Vec<(String, Vec<Vec<String>>)>,
}

/// One model's SQL rule inputs.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ModelKeyInput<'a> {
    pub authored_sql: &'a str,
    pub query_sql: &'a str,
    /// The model's dynamic column contract in a canonical text form, if it has one.
    pub contract: Option<&'a str>,
}

/// One stored entry: the key it was computed for and its findings as JSON values.
#[derive(Clone, Debug, PartialEq)]
pub struct CachedEntry {
    pub identity: String,
    pub findings: Vec<serde_json::Value>,
}

/// The stored findings of each path whose key still matches, and every other path.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct CacheLookup {
    pub hits: Vec<(String, Vec<serde_json::Value>)>,
    pub misses: Vec<String>,
}
