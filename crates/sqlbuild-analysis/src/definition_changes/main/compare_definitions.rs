//! The nodes that changed between a base and a current definition snapshot.

use std::collections::{BTreeMap, BTreeSet};

use crate::definition_changes::_helpers::aspects::changed_aspects;
use crate::definition_changes::main::node_key::node_key;
use crate::definition_changes::models::{
    DefinitionChanges, DefinitionSnapshot, DeletedNode, NodeChange, NodeDefinition,
};

/// The base node a current node renamed through `migrate_from`, if one is unclaimed.
fn renamed_base<'a>(
    current_key: &str,
    node: &NodeDefinition,
    (base, current): (&'a DefinitionSnapshot, &DefinitionSnapshot),
    claimed: &BTreeSet<String>,
) -> Option<(String, &'a NodeDefinition)> {
    for old_name in &node.migrate_from {
        let old_key: String = node_key(&node.kind, old_name);
        if old_key == current_key
            || claimed.contains(&old_key)
            || current.nodes.contains_key(&old_key)
        {
            continue;
        }
        if let Some(definition) = base.nodes.get(&old_key) {
            return Some((old_key, definition));
        }
    }
    None
}

/// Added nodes are changed, deleted ones listed; a `migrate_from` rename changes only with its definition.
pub fn compare_definitions(
    base: &DefinitionSnapshot,
    current: &DefinitionSnapshot,
) -> DefinitionChanges {
    let mut changed: BTreeMap<String, NodeChange> = BTreeMap::new();
    let mut renamed: Vec<(String, String)> = Vec::new();
    let mut claimed: BTreeSet<String> = BTreeSet::new();
    for (key, node) in &current.nodes {
        let change = |added: bool, aspects: Vec<String>, renamed_from: Option<String>| NodeChange {
            kind: node.kind.clone(),
            name: node.name.clone(),
            added,
            aspects,
            renamed_from,
        };
        if let Some(previous) = base.nodes.get(key) {
            let aspects: Vec<String> = changed_aspects(previous, node);
            if !aspects.is_empty() {
                changed.insert(key.clone(), change(false, aspects, None));
            }
            continue;
        }
        match renamed_base(key, node, (base, current), &claimed) {
            Some((old_key, previous)) => {
                let aspects: Vec<String> = changed_aspects(previous, node);
                if !aspects.is_empty() {
                    changed.insert(
                        key.clone(),
                        change(false, aspects, Some(previous.name.clone())),
                    );
                }
                claimed.insert(old_key.clone());
                renamed.push((old_key, key.clone()));
            }
            None => {
                changed.insert(key.clone(), change(true, Vec::new(), None));
            }
        }
    }
    let mut deleted: Vec<DeletedNode> = base
        .nodes
        .iter()
        .filter(|(key, _)| !current.nodes.contains_key(*key) && !claimed.contains(*key))
        .map(|(_, node)| DeletedNode {
            kind: node.kind.clone(),
            name: node.name.clone(),
        })
        .collect();
    deleted.sort();
    DefinitionChanges {
        changed,
        deleted,
        renamed,
    }
}
