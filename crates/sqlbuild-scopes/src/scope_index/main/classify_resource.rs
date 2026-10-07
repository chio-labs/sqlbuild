//! Python's `_classify_resource`: ordered visible records and inaccessible positions.

use std::collections::HashMap;

use crate::scope_index::_helpers::consumer_positions::visible_positions;
use crate::scope_index::models::{
    ConsumerResource, GrantEntry, ResourceVisibility, ScopeDeferral, VisibilityReason,
    VisibilityTable, VisibleEntry,
};

/// Classify every declaration for one resource as Python does; rejected paths defer.
pub fn classify_resource(
    table: &VisibilityTable,
    resource: &ConsumerResource,
) -> Result<ResourceVisibility, ScopeDeferral> {
    let positive: Vec<(usize, VisibilityReason)> = visible_positions(table, resource)?;
    if resource.grants.is_empty() {
        let mut visible_positions: Vec<bool> = vec![false; table.identity_keys.len()];
        for (position, _) in &positive {
            visible_positions[*position] = true;
        }
        return Ok(ResourceVisibility {
            visible: positive
                .iter()
                .map(|(position, reason)| VisibleEntry {
                    position: *position,
                    reason: *reason,
                    through: None,
                })
                .collect(),
            inaccessible: (0..table.identity_keys.len())
                .filter(|position| !visible_positions[*position])
                .collect(),
        });
    }
    let mut reasons: HashMap<usize, VisibilityReason> = HashMap::new();
    for (position, reason) in &positive {
        reasons.insert(*position, *reason);
    }
    let mut grants_by_identity: HashMap<u32, Vec<GrantEntry>> = HashMap::new();
    for grant in &resource.grants {
        grants_by_identity
            .entry(grant.identity_key)
            .or_default()
            .push(*grant);
    }
    let mut classified: ResourceVisibility = ResourceVisibility::default();
    for (position, identity_key) in table.identity_keys.iter().enumerate() {
        let reason: Option<VisibilityReason> = reasons.get(&position).copied();
        if let Some(reason) = reason {
            classified.visible.push(VisibleEntry {
                position,
                reason,
                through: None,
            });
        }
        match grants_by_identity.get(identity_key) {
            Some(grants) => classified
                .visible
                .extend(grants.iter().map(|grant| VisibleEntry {
                    position,
                    reason: grant.reason,
                    through: Some(grant.through),
                })),
            None if reason.is_none() => classified.inaccessible.push(position),
            None => {}
        }
    }
    Ok(classified)
}
