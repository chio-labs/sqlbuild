//! What one model migration decision does.

use crate::migration_values::constants::{BLOCKING_DECISIONS, CONFLICT_DECISION, MOVING_DECISIONS};
use crate::migration_values::models::DecisionTraits;

/// The behaviour of the model migration decision whose value is `decision`.
#[must_use]
pub fn migration_decision_traits(decision: &str) -> DecisionTraits {
    let moves_data: bool = MOVING_DECISIONS.contains(&decision);
    DecisionTraits {
        moves_data,
        blocks_build: BLOCKING_DECISIONS.contains(&decision),
        checks_compatibility: moves_data || decision == CONFLICT_DECISION,
    }
}
