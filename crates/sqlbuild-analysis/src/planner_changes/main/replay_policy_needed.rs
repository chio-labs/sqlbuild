//! Whether a change reads the model's replay policy.

use crate::planner_changes::_helpers::schema_comparer::schema_replays;
use crate::planner_changes::models::BackfillFacts;

/// Query and function changes read `replay_on_change`, and so do schema findings that come with a definition change.
pub fn replay_policy_needed(facts: BackfillFacts) -> bool {
    facts.query_changed || facts.functions_changed || schema_replays(facts)
}
