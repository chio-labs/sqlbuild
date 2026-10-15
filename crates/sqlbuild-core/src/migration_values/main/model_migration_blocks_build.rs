//! Whether one planned model migration stops a build before any execution.

use crate::migration_values::models::ModelMigrationFacts;

/// A missing origin blocks when tracked or denied; otherwise the decision or an incompatible move blocks.
#[must_use]
pub fn model_migration_blocks_build(facts: &ModelMigrationFacts) -> bool {
    if facts.origin_missing {
        return facts.origin_tracked || facts.deny_missing_origin;
    }
    facts.decision.blocks_build || (facts.decision.moves_data && facts.incompatible)
}
