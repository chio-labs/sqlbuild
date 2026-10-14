//! Combined graph keys, inputs and selection results.

use std::collections::{BTreeSet, HashMap, HashSet};

use crate::dbt_graph::constants::{
    DBT_OWNER, MODEL_RESOURCE_TYPE, SOURCE_RESOURCE_TYPE, SQLBUILD_OWNER,
};

/// The namespace that owns a graph node.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum DbtGraphOwner {
    Dbt,
    Sqlbuild,
}

/// The resource type namespace of a graph node.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum DbtGraphResourceType {
    Model,
    Source,
}

/// One owner-qualified combined graph node.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct DbtGraphKey {
    pub owner: DbtGraphOwner,
    pub resource_type: DbtGraphResourceType,
    pub name: String,
}

impl DbtGraphKey {
    /// The key of one dbt model.
    #[must_use]
    pub fn dbt_model(unique_id: &str) -> Self {
        Self {
            owner: DbtGraphOwner::Dbt,
            resource_type: DbtGraphResourceType::Model,
            name: unique_id.to_owned(),
        }
    }

    /// The key of one dbt source or seed.
    #[must_use]
    pub fn dbt_source(unique_id: &str) -> Self {
        Self {
            owner: DbtGraphOwner::Dbt,
            resource_type: DbtGraphResourceType::Source,
            name: unique_id.to_owned(),
        }
    }

    /// The key of one SQLBuild model.
    #[must_use]
    pub fn sqlbuild_model(name: &str) -> Self {
        Self {
            owner: DbtGraphOwner::Sqlbuild,
            resource_type: DbtGraphResourceType::Model,
            name: name.to_owned(),
        }
    }

    /// `owner:resource_type:name`, the order graph edges are sorted by.
    #[must_use]
    pub fn stable_id(&self) -> String {
        let owner: &str = match self.owner {
            DbtGraphOwner::Dbt => DBT_OWNER,
            DbtGraphOwner::Sqlbuild => SQLBUILD_OWNER,
        };
        let resource_type: &str = match self.resource_type {
            DbtGraphResourceType::Model => MODEL_RESOURCE_TYPE,
            DbtGraphResourceType::Source => SOURCE_RESOURCE_TYPE,
        };
        format!("{owner}:{resource_type}:{}", self.name)
    }
}

/// Directed edges keyed by node, in first-insertion node order.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DbtGraphEdges {
    pub order: Vec<DbtGraphKey>,
    pub targets: HashMap<DbtGraphKey, Vec<DbtGraphKey>>,
}

/// The combined graph with upstream and downstream edges sorted by stable ID.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DbtCombinedGraph {
    pub upstream: DbtGraphEdges,
    pub downstream: DbtGraphEdges,
}

/// One dbt model of the manifest index.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DbtGraphManifestModel {
    pub unique_id: String,
    pub name: String,
    pub depends_on_nodes: Vec<String>,
}

/// The manifest nodes the graph reads, models in index order.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DbtGraphManifest {
    pub models: Vec<DbtGraphManifestModel>,
    pub source_ids: HashSet<String>,
    pub seed_ids: HashSet<String>,
}

/// One compiled SQLBuild model: its SQLBuild model dependencies and resolved dbt refs.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DbtGraphProjectModel {
    pub name: String,
    pub model_deps: Vec<String>,
    pub dbt_ref_unique_ids: Vec<String>,
}

/// One selector term split into its core and expansion markers.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DbtSelectorExpansion {
    pub core: String,
    pub upstream: bool,
    pub downstream: bool,
}

/// The selector terms and dbt anchors one `sqb dbt` selection resolves.
#[derive(Clone, Copy, Debug)]
pub struct DbtSelectionRequest<'a> {
    pub select: &'a [String],
    pub exclude: &'a [String],
    pub anchor_unique_ids_by_term: &'a HashMap<String, Vec<String>>,
    /// Manifest models as `(unique_id, name)` in index order, when a manifest is loaded.
    pub manifest_models: Option<&'a [(String, String)]>,
}

/// Selected SQLBuild models and the dbt nodes they require.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DbtSelection {
    pub sqlbuild_model_names: Vec<String>,
    pub dbt_required_unique_ids: Vec<String>,
    pub dbt_anchor_terms: Vec<String>,
    pub dbt_anchor_unique_ids_by_term: Vec<(String, Vec<String>)>,
    pub path_translations: Vec<(String, String)>,
}

/// Selection accumulated over the terms resolved so far.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DbtSelectionState {
    pub sqlbuild: BTreeSet<String>,
    pub dbt: BTreeSet<String>,
    pub selection: DbtSelection,
}
