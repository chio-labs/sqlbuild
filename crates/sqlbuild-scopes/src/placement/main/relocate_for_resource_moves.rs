//! The declarations whose placement follows several resources to new paths.

use std::collections::HashSet;

use crate::placement::_helpers::relocation::{changed_records, moved_resources, relocation_round};
use crate::placement::main::placement_diagnostics::placement_diagnostics;
use crate::placement::models::{PlacementIndex, Relocation};
use crate::scope_index::models::{DeclarationIdentity, ResourceIdentity};

/// Each declaration moved once every resource in `moves` is at its destination, or `None`.
#[must_use]
pub fn relocate_for_resource_moves(
    index: &PlacementIndex,
    moves: &[(ResourceIdentity, String)],
) -> Option<Vec<Relocation>> {
    let misplaced: HashSet<&DeclarationIdentity> = placement_diagnostics(index)
        .into_iter()
        .map(|diagnostic| &index.declarations[diagnostic.declaration].identity)
        .collect();
    let mut current: PlacementIndex = moved_resources(index, moves);
    let mut requires_group: HashSet<DeclarationIdentity> = HashSet::new();
    for _ in 0..=index.declarations.len() {
        let (relocated, grouping) = relocation_round(&current, &misplaced);
        for (identity, needed) in grouping {
            if needed {
                requires_group.insert(identity);
            } else {
                requires_group.remove(&identity);
            }
        }
        if relocated.is_empty() {
            return Some(changed_records(index, &current, &requires_group));
        }
        for record in &mut current.declarations {
            if let Some(moved) = relocated.get(&record.identity) {
                *record = moved.clone();
            }
        }
    }
    None
}
