//! Suggest declarations for output columns resembling removed live columns.

use std::collections::BTreeSet;

use crate::planner_migrations::_helpers::proofs::removed_and_added::removed_and_added;
use crate::planner_migrations::models::{Projection, RenameHint};

/// Hints ordered by added projection, preferring identical expressions over shared references.
pub fn rename_hints(
    shapes: (&[Projection], &[Projection]),
    excluded: &BTreeSet<String>,
    live_columns: &BTreeSet<String>,
    same_binding: bool,
) -> Vec<RenameHint> {
    let (removed, added) = removed_and_added(shapes, excluded);
    let live_removed: Vec<&Projection> = removed
        .into_iter()
        .filter(|origin| live_columns.contains(&origin.key))
        .collect();
    let mut hints: Vec<RenameHint> = Vec::new();
    for column in added {
        if live_columns.contains(&column.key) {
            continue;
        }
        let identical: Vec<String> = live_removed
            .iter()
            .filter(|origin| same_binding && origin.expression == column.expression)
            .map(|origin| origin.name.clone())
            .collect();
        let similar: Vec<String> = live_removed
            .iter()
            .filter(|origin| {
                !origin.references.is_empty() && origin.references == column.references
            })
            .map(|origin| origin.name.clone())
            .collect();
        if !identical.is_empty() || !similar.is_empty() {
            hints.push(RenameHint {
                added_column: column.name.clone(),
                identical: !identical.is_empty(),
                candidate_columns: if identical.is_empty() {
                    similar
                } else {
                    identical
                },
            });
        }
    }
    hints
}
