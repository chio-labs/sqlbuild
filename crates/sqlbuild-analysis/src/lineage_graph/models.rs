//! Column lineage graph edges and their indexes.

use std::collections::HashMap;

/// One collapsed edge's identity, every part as Python's `str()` renders it.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct EdgeKey {
    pub source_type: String,
    pub source_name: String,
    pub source_column: String,
    pub target_model: String,
    pub target_column: String,
    pub transform: String,
    pub confidence: String,
}

/// Edge positions by target model and source resource, and each edge's first equal edge.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct EdgeIndex {
    pub by_target_model: HashMap<String, Vec<usize>>,
    pub by_source_resource: HashMap<String, Vec<usize>>,
    pub first_equal: Vec<usize>,
}

/// How an adapter dialect name maps onto a Polyglot analysis dialect.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AnalysisDialect<'a> {
    /// A known alias of this Polyglot dialect value.
    Alias(&'static str),
    /// Not an alias: the name itself must be a Polyglot dialect value.
    Named(&'a str),
}

/// One tree line: its node, indent, branch, and whether the node was already shown.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TreeLine<'a, N> {
    pub node: &'a N,
    pub prefix: &'a str,
    pub branch: &'static str,
    pub repeated: bool,
}
