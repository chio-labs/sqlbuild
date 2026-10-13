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
