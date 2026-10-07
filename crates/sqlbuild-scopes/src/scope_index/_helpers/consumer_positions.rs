//! Python's `_visible_positions`: positions a resource sees by scope, sorted.

use crate::scope_index::_helpers::paths::{canonical_ancestors, parent};
use crate::scope_index::models::{
    ConsumerResource, ScopeDeferral, VisibilityReason, VisibilityTable,
};

/// Return `(position, reason)` pairs sorted as Python sorts its tuples.
pub(crate) fn visible_positions(
    table: &VisibilityTable,
    resource: &ConsumerResource,
) -> Result<Vec<(usize, VisibilityReason)>, ScopeDeferral> {
    let mut positive: Vec<(usize, VisibilityReason)> = table
        .global
        .iter()
        .map(|position| (*position, VisibilityReason::Global))
        .collect();
    positive.extend(
        resource
            .private
            .iter()
            .map(|position| (*position, VisibilityReason::PrivateOwner)),
    );
    if !table.local.is_empty() || !table.inherited.is_empty() {
        let parent: String = parent(&resource.path)?;
        if let Some(positions) = table.local.get(&parent) {
            positive.extend(
                positions
                    .iter()
                    .map(|position| (*position, VisibilityReason::LocalOwner)),
            );
        }
        for ancestor in canonical_ancestors(&parent) {
            if let Some(positions) = table.inherited.get(ancestor) {
                positive.extend(
                    positions
                        .iter()
                        .map(|position| (*position, VisibilityReason::InheritedAncestor)),
                );
            }
        }
    }
    positive.sort_by(|left, right| {
        left.0
            .cmp(&right.0)
            .then_with(|| left.1.as_str().cmp(right.1.as_str()))
    });
    Ok(positive)
}
