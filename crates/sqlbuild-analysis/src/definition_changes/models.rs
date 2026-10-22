//! Definition snapshots, the changes between two of them, and what a test or scenario executes.

use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};

/// The definition fingerprint of one project node.
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct NodeDefinition {
    pub kind: String,
    pub name: String,
    /// The digest of each part of the definition, by aspect name.
    pub aspects: BTreeMap<String, String>,
    /// Keys of the macros, enums and constants the node uses, resolved through scopes.
    #[serde(default)]
    pub uses: Vec<String>,
    /// Names the node was renamed from, as its `migrate_from` declares them.
    #[serde(default)]
    pub migrate_from: Vec<String>,
}

/// Every node definition of one compiled project revision, by node key.
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct DefinitionSnapshot {
    pub format: u32,
    pub nodes: BTreeMap<String, NodeDefinition>,
}

/// How one node differs from the base revision.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct NodeChange {
    pub kind: String,
    pub name: String,
    /// The node did not exist at the base revision.
    pub added: bool,
    /// The aspects whose digests differ, in aspect order; empty for an added node.
    pub aspects: Vec<String>,
    /// The base name of a node its `migrate_from` renamed.
    pub renamed_from: Option<String>,
}

/// A base node that no longer exists.
#[derive(Clone, Debug, Default, PartialEq, Eq, PartialOrd, Ord)]
pub struct DeletedNode {
    pub kind: String,
    pub name: String,
}

/// The nodes that changed between a base and a current snapshot.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DefinitionChanges {
    /// Added and modified nodes, by current node key.
    pub changed: BTreeMap<String, NodeChange>,
    /// Base nodes absent from the current revision, which select nothing.
    pub deleted: Vec<DeletedNode>,
    /// `(base key, current key)` of renames that `migrate_from` declares.
    pub renamed: Vec<(String, String)>,
}

/// What one test or scenario depends on, honouring what it mocks.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ExecutedItem {
    /// Keys of the item's own definition, such as its test file.
    pub own_keys: Vec<String>,
    /// Keys of the models, seeds and functions it really executes, in execution order.
    pub executed: Vec<String>,
    /// Keys of the macros, enums and constants its own SQL uses.
    pub declarations: Vec<String>,
    /// Keys of declarations the item mocks, whose changes never select it.
    pub mocked: BTreeSet<String>,
    /// Keys of relations the item mocks, whose declared columns still shape the mock.
    pub mocked_relations: Vec<String>,
}

/// One selected test or scenario and why it was selected.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct SelectedItem {
    pub label: String,
    pub reasons: Vec<String>,
}
