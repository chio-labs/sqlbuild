//! The project graph a diff selection resolves over, with resources as indexes.

/// Selectable names, lineage edges and selector indexes over resource indexes.
#[derive(Debug, Clone, Default)]
pub struct DiffGraph {
    /// `(name, resource)` of models, then sources, then seeds; a later name wins.
    pub names: Vec<(String, usize)>,
    /// Each resource's upstream resources.
    pub upstream: Vec<Vec<usize>>,
    /// Each resource's downstream resources.
    pub downstream: Vec<Vec<usize>>,
    /// `(tag, resources)`.
    pub tags: Vec<(String, Vec<usize>)>,
    /// `(resource, model folder)`.
    pub paths: Vec<(usize, String)>,
}

/// The parsed shape of one raw diff query: lowercased expression kinds and write clauses.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct RawQueryShape {
    pub root_key: String,
    /// Every node kind in depth-first order, collected only for read-only roots.
    pub node_keys: Vec<String>,
    /// The root `SELECT` has an `INTO` target or row-locking clauses.
    pub writes_or_locks: bool,
}
