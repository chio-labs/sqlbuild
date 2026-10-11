//! The placement every declaration's consumers require, resolved over one shared anchor pass.

use std::collections::{HashMap, HashSet};

use crate::placement::_helpers::anchors::{
    AnchorSets, UsagesByDeclaration, anchor_sets, usages_by_declaration,
};
use crate::placement::_helpers::required::required_placement;
use crate::placement::models::{PlacementIndex, RequiredPlacement};
use crate::scope_index::models::DeclarationIdentity;

/// Python's `resolve_required_placement` for each identity's first record, where it has one.
#[must_use]
pub fn required_declaration_placements(
    index: &PlacementIndex,
) -> HashMap<DeclarationIdentity, RequiredPlacement> {
    let usages: UsagesByDeclaration<'_> = usages_by_declaration(index);
    let anchors: AnchorSets = anchor_sets(index, &usages);
    let mut placements: HashMap<DeclarationIdentity, RequiredPlacement> = HashMap::new();
    let mut seen: HashSet<&DeclarationIdentity> = HashSet::new();
    for record in &index.declarations {
        if !seen.insert(&record.identity) {
            continue;
        }
        if let Some(placement) = required_placement(record, &usages, &anchors) {
            placements.insert(record.identity.clone(), placement);
        }
    }
    placements
}
