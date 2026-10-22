//! Why a test or scenario is affected by the changes since the base revision.

use std::collections::BTreeSet;

use crate::definition_changes::_helpers::aspects::{aspect_label, joined, kind_words};
use crate::definition_changes::constants::{CONSTANT_KIND, ENUM_KIND, MODEL_KIND, TEST_FILE_KIND};
use crate::definition_changes::models::{
    DefinitionChanges, DefinitionSnapshot, ExecutedItem, NodeChange,
};

fn aspect_phrase(change: &NodeChange) -> String {
    let labels: Vec<String> = change
        .aspects
        .iter()
        .map(|aspect| aspect_label(aspect).to_owned())
        .collect();
    joined(&labels)
}

/// `test file changed`, `scenario file and snapshots changed`, `test file added`.
fn own_reason(change: &NodeChange) -> String {
    let (singular, _) = kind_words(&change.kind);
    if change.added {
        return format!("{singular} added");
    }
    if change.kind == TEST_FILE_KIND {
        return format!("{singular} changed");
    }
    format!("{singular} {} changed", aspect_phrase(change))
}

/// `added`, `model SQL changed`, `renamed from old_orders, config changed`, `changed`.
fn change_detail(change: &NodeChange) -> String {
    if change.added {
        return "added".to_owned();
    }
    let detail: String = if change.kind == MODEL_KIND {
        format!("model {} changed", aspect_phrase(change))
    } else {
        "changed".to_owned()
    };
    match &change.renamed_from {
        Some(old_name) => format!("renamed from {old_name}, {detail}"),
        None => detail,
    }
}

fn executed_reason(change: &NodeChange) -> String {
    let subject: String = if change.kind == MODEL_KIND {
        change.name.clone()
    } else {
        format!("{} {}", kind_words(&change.kind).0, change.name)
    };
    format!("executes {subject} ({})", change_detail(change))
}

fn declaration_reason(change: &NodeChange) -> String {
    let verb: &str = if change.kind == ENUM_KIND || change.kind == CONSTANT_KIND {
        "uses"
    } else {
        "executes"
    };
    format!(
        "{verb} {} {} ({})",
        kind_words(&change.kind).0,
        change.name,
        change_detail(change)
    )
}

/// Declarations `item` reaches through its own SQL and its executed nodes, transitively,
/// without the ones it mocks.
fn reached_declarations(item: &ExecutedItem, current: &DefinitionSnapshot) -> BTreeSet<String> {
    let mut pending: Vec<String> = item.declarations.clone();
    for key in &item.executed {
        if let Some(node) = current.nodes.get(key) {
            pending.extend(node.uses.iter().cloned());
        }
    }
    let mut reached: BTreeSet<String> = BTreeSet::new();
    while let Some(key) = pending.pop() {
        if item.mocked.contains(&key) || !reached.insert(key.clone()) {
            continue;
        }
        if let Some(node) = current.nodes.get(&key) {
            pending.extend(node.uses.iter().cloned());
        }
    }
    reached
}

/// One reason per changed node `item` depends on: its own definition first, then executed
/// nodes in execution order, then declarations by key. Empty when nothing it runs changed.
pub fn selection_reasons(
    item: &ExecutedItem,
    current: &DefinitionSnapshot,
    changes: &DefinitionChanges,
) -> Vec<String> {
    let mut reasons: Vec<String> = Vec::new();
    let mut push = |reason: String| {
        if !reasons.contains(&reason) {
            reasons.push(reason);
        }
    };
    for key in &item.own_keys {
        if let Some(change) = changes.changed.get(key) {
            push(own_reason(change));
        }
    }
    for key in &item.executed {
        if let Some(change) = changes.changed.get(key) {
            push(executed_reason(change));
        }
    }
    for key in reached_declarations(item, current) {
        if let Some(change) = changes.changed.get(&key) {
            push(declaration_reason(change));
        }
    }
    reasons
}
