//! The project graph, the resources it is built from and selector failures.

use std::collections::HashMap;

use crate::assembly::project::types::ObjectKey;

/// One graph resource in project order: its key, upstream keys, tags and model folder.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct GraphResource {
    pub key: ObjectKey,
    pub deps: Vec<ObjectKey>,
    pub tags: Vec<String>,
    /// A model's folder below `models/`; `None` for every other resource.
    pub folder: Option<String>,
}

/// Python's `ProjectGraph` indexes, each in Python's dict insertion order.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ProjectGraph {
    /// Lineage edges with SQL tests stripped.
    pub upstream: Vec<(ObjectKey, Vec<ObjectKey>)>,
    /// Inverted edges, each list sorted by `(resource type, name)`.
    pub downstream: Vec<(ObjectKey, Vec<ObjectKey>)>,
    /// Tag to keys, keys in first-tagged order.
    pub tags: Vec<(String, Vec<ObjectKey>)>,
    /// Model key to its folder below `models/`.
    pub paths: Vec<(ObjectKey, String)>,
    /// Selector name to key; a later resource with the same name replaces the key in place.
    pub names: Vec<(String, ObjectKey)>,
    pub(crate) upstream_index: HashMap<ObjectKey, usize>,
    pub(crate) downstream_index: HashMap<ObjectKey, usize>,
    pub(crate) name_index: HashMap<String, usize>,
}

/// Python's `PlannerInputError` for a selector: code, message and optional help.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SelectorError {
    pub code: &'static str,
    pub message: String,
    pub help: Option<String>,
}
