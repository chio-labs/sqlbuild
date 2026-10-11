//! The exact placement a declaration's consumers require, with validation's anchor semantics.

use crate::placement::_helpers::anchors::{
    AnchorSets, UsagesByDeclaration, anchor_sets, usages_by_declaration,
};
use crate::placement::_helpers::required::required_placement;
use crate::placement::models::{PlacementIndex, RequiredPlacement};
use crate::scope_index::models::{DeclarationIdentity, DeclarationRecord};

/// Python's `resolve_required_placement` for the first record of `declaration`.
#[must_use]
pub fn required_declaration_placement(
    index: &PlacementIndex,
    declaration: &DeclarationIdentity,
) -> Option<RequiredPlacement> {
    let record: &DeclarationRecord = index
        .declarations
        .iter()
        .find(|record| &record.identity == declaration)?;
    let usages: UsagesByDeclaration<'_> = usages_by_declaration(index);
    let anchors: AnchorSets = anchor_sets(index, &usages);
    required_placement(record, &usages, &anchors)
}
