//! The reason texts of selected tests and the declarations an executed item reaches.

use std::collections::BTreeSet;

use crate::definition_changes::_helpers::aspects::{aspect_label, joined, kind_words};
use crate::definition_changes::constants::{
    COLUMNS_ASPECT, CONNECTION_KIND, CONSTANT_KIND, DEPENDENCIES_KIND, ENUM_KIND, MODEL_KIND,
    SEED_KIND, SETTINGS_KIND, SOURCE_KIND, TEST_FILE_KIND,
};

/// Project-wide kinds whose reasons name the kind, not the single node.
const PROJECT_WIDE_KINDS: [&str; 3] = [SETTINGS_KIND, CONNECTION_KIND, DEPENDENCIES_KIND];
use crate::definition_changes::models::{DefinitionSnapshot, ExecutedItem, NodeChange};

fn aspect_phrase(change: &NodeChange) -> String {
    let labels: Vec<String> = change
        .aspects
        .iter()
        .map(|aspect| aspect_label(aspect).to_owned())
        .collect();
    joined(&labels)
}

/// `test file changed`, `scenario file and snapshots changed`, `test file added`.
pub(crate) fn own_reason(change: &NodeChange) -> String {
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

/// `executes stg_orders (model SQL changed)`, `reads seed countries (changed)`.
pub(crate) fn executed_reason(change: &NodeChange) -> String {
    let subject: String = if change.kind == MODEL_KIND {
        change.name.clone()
    } else {
        format!("{} {}", kind_words(&change.kind).0, change.name)
    };
    let verb: &str = if change.kind == SEED_KIND || change.kind == SOURCE_KIND {
        "reads"
    } else {
        "executes"
    };
    format!("{verb} {subject} ({})", change_detail(change))
}

/// `executes macro to_utc (changed)`, `uses enum status (changed)`, `uses project settings (changed)`.
pub(crate) fn declaration_reason(change: &NodeChange) -> String {
    if PROJECT_WIDE_KINDS.contains(&change.kind.as_str()) {
        return format!(
            "uses {} ({})",
            kind_words(&change.kind).0,
            change_detail(change)
        );
    }
    if change.kind == SOURCE_KIND {
        return executed_reason(change);
    }
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

/// Declarations `item` reaches, transitively through its SQL and executed nodes, minus its mocks.
pub(crate) fn reached_declarations(
    item: &ExecutedItem,
    current: &DefinitionSnapshot,
) -> BTreeSet<String> {
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

/// `mocks stg_orders (model columns changed)` when a mocked relation's declared shape changed.
pub(crate) fn mocked_reason(change: &NodeChange) -> Option<String> {
    if !change.added && !change.aspects.iter().any(|aspect| aspect == COLUMNS_ASPECT) {
        return None;
    }
    let subject: String = if change.kind == MODEL_KIND {
        change.name.clone()
    } else {
        format!("{} {}", kind_words(&change.kind).0, change.name)
    };
    let detail: String = if change.added {
        "added".to_owned()
    } else {
        format!("{} columns changed", kind_words(&change.kind).0)
    };
    Some(format!("mocks {subject} ({detail})"))
}
