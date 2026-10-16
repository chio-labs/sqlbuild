//! What one column migration decision does.

use crate::migration_values::constants::{
    BLOCKING_COLUMN_DECISIONS, COLUMN_DECISION_LABELS, RECORDING_COLUMN_DECISIONS,
    RENAME_COLUMN_DECISION,
};
use crate::migration_values::models::ColumnDecisionTraits;

/// The behaviour of the column migration decision whose value is `decision`.
#[must_use]
pub fn column_decision_traits(decision: &str) -> ColumnDecisionTraits {
    ColumnDecisionTraits {
        renames: decision == RENAME_COLUMN_DECISION,
        records_event: RECORDING_COLUMN_DECISIONS.contains(&decision),
        blocks_build: BLOCKING_COLUMN_DECISIONS.contains(&decision),
        label: COLUMN_DECISION_LABELS
            .iter()
            .find(|(value, _)| *value == decision)
            .map(|(_, label)| *label),
    }
}
