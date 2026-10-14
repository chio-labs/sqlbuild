//! Match output membership without changing projection order.

use std::collections::BTreeSet;

use crate::planner_migrations::models::Projection;

/// Previous-only and current-only projections, excluding declared migrations.
pub(crate) fn removed_and_added<'a>(
    (previous, current): (&'a [Projection], &'a [Projection]),
    excluded: &BTreeSet<String>,
) -> (Vec<&'a Projection>, Vec<&'a Projection>) {
    let previous_names: BTreeSet<&str> = previous.iter().map(|item| item.key.as_str()).collect();
    let current_names: BTreeSet<&str> = current.iter().map(|item| item.key.as_str()).collect();
    let removed: Vec<&Projection> = previous
        .iter()
        .filter(|item| !current_names.contains(item.key.as_str()) && !excluded.contains(&item.key))
        .collect();
    let added: Vec<&Projection> = current
        .iter()
        .filter(|item| !previous_names.contains(item.key.as_str()) && !excluded.contains(&item.key))
        .collect();
    (removed, added)
}
