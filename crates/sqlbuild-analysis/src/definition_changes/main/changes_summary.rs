//! A one-line account of what changed since the base revision.

use std::collections::BTreeMap;

use crate::definition_changes::_helpers::aspects::kind_words;
use crate::definition_changes::constants::KIND_LABELS;
use crate::definition_changes::models::DefinitionChanges;

fn kind_rank(kind: &str) -> usize {
    KIND_LABELS
        .iter()
        .position(|(name, _, _)| *name == kind)
        .unwrap_or(KIND_LABELS.len())
}

fn counted<'a>(kinds: impl Iterator<Item = &'a str>) -> Option<String> {
    let mut counts: BTreeMap<(usize, &str), usize> = BTreeMap::new();
    for kind in kinds {
        *counts.entry((kind_rank(kind), kind)).or_default() += 1;
    }
    if counts.is_empty() {
        return None;
    }
    let parts: Vec<String> = counts
        .into_iter()
        .map(|((_, kind), count)| {
            let (singular, plural) = kind_words(kind);
            if count == 1 {
                format!("1 {singular}")
            } else {
                format!("{count} {plural}")
            }
        })
        .collect();
    Some(parts.join(", "))
}

/// `2 models, 1 macro changed; 1 seed added; deleted: model old_orders`, or `no definition changes`.
pub fn changes_summary(changes: &DefinitionChanges) -> String {
    let mut parts: Vec<String> = Vec::new();
    let modified = changes.changed.values().filter(|change| !change.added);
    if let Some(text) = counted(modified.map(|change| change.kind.as_str())) {
        parts.push(format!("{text} changed"));
    }
    let added = changes.changed.values().filter(|change| change.added);
    if let Some(text) = counted(added.map(|change| change.kind.as_str())) {
        parts.push(format!("{text} added"));
    }
    let mut renamed: Vec<&str> = Vec::new();
    for (_, key) in &changes.renamed {
        if let Some((kind, _)) = key.split_once(':') {
            renamed.push(kind);
        }
    }
    if let Some(text) = counted(renamed.into_iter()) {
        parts.push(format!("{text} renamed"));
    }
    if !changes.deleted.is_empty() {
        let names: Vec<String> = changes
            .deleted
            .iter()
            .map(|node| format!("{} {}", kind_words(&node.kind).0, node.name))
            .collect();
        parts.push(format!("deleted: {}", names.join(", ")));
    }
    if parts.is_empty() {
        return "no definition changes".to_owned();
    }
    parts.join("; ")
}
