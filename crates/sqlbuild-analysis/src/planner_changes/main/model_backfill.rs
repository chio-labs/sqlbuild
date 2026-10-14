//! Resolve the backfill of a detected change.

use crate::planner_changes::_helpers::pick_more_aggressive::pick_more_aggressive;
use crate::planner_changes::_helpers::schema_comparer::schema_replays;
use crate::planner_changes::models::{Backfill, BackfillAction, BackfillFacts};

/// The replay policy applies to query or function changes, and to schema findings that come with any definition change; `replay` is the resolved policy, present when `replay_policy_needed`.
pub fn model_backfill(facts: BackfillFacts, replay: Option<Backfill>) -> Backfill {
    let forward = Backfill {
        action: BackfillAction::ForwardOnly,
        duration: None,
    };
    let Some(replay) = replay else {
        return forward;
    };
    let definition: Backfill = if facts.query_changed || facts.functions_changed {
        replay.clone()
    } else {
        forward.clone()
    };
    let schema: Backfill = if schema_replays(facts) {
        replay
    } else {
        forward
    };
    pick_more_aggressive(definition, schema)
}
