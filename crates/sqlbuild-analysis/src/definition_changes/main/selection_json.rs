//! The `since` section of a `--since` run's JSON document.

use serde_json::{Value, json};

use crate::definition_changes::models::{DefinitionChanges, SelectedItem};

/// The ref, merge base, changed, renamed and deleted nodes, and each selected item with its reasons.
pub fn selection_json(
    (reference, merge_base): (&str, &str),
    changes: &DefinitionChanges,
    (total, selected): (usize, &[SelectedItem]),
) -> Value {
    let changed: Vec<Value> = changes
        .changed
        .values()
        .map(|change| {
            json!({
                "kind": change.kind,
                "name": change.name,
                "added": change.added,
                "aspects": change.aspects,
                "renamed_from": change.renamed_from,
            })
        })
        .collect();
    let renamed: Vec<Value> = changes
        .renamed
        .iter()
        .map(|(from, to)| {
            let (kind, old_name) = from.split_once(':').unwrap_or_default();
            let new_name: &str = to.split_once(':').map_or(to.as_str(), |(_, name)| name);
            json!({ "kind": kind, "from": old_name, "to": new_name })
        })
        .collect();
    let deleted: Vec<Value> = changes
        .deleted
        .iter()
        .map(|node| json!({ "kind": node.kind, "name": node.name }))
        .collect();
    let items: Vec<Value> = selected
        .iter()
        .map(|item| json!({ "name": item.label, "reasons": item.reasons }))
        .collect();
    json!({
        "ref": reference,
        "merge_base": merge_base,
        "changed": changed,
        "renamed": renamed,
        "deleted": deleted,
        "candidate_count": total,
        "selected": items,
    })
}
