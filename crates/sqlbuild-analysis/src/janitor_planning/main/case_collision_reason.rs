//! Relations whose folded name is shared in their listing.

use std::collections::HashSet;

use crate::janitor_planning::constants::CASE_COLLISION_REASON;

/// Why a relation must not be dropped because its folded name collides, if it does.
#[must_use]
pub fn case_collision_reason(
    name: &str,
    colliding_names: &HashSet<String>,
) -> Option<&'static str> {
    colliding_names
        .contains(&name.to_lowercase())
        .then_some(CASE_COLLISION_REASON)
}
