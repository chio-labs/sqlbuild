//! Why an incremental model is planned as a full rebuild.

use crate::planner_warehouse::constants::{CHANGE_KIND_FIRST_RUN, CHANGE_KIND_RENAMED};
use crate::planner_warehouse::models::FullRebuildFacts;

/// The cause text shown in plans and full-refresh refusals.
pub fn full_rebuild_cause(facts: &FullRebuildFacts) -> String {
    if facts.full_refresh {
        "--full-refresh".to_owned()
    } else if facts.change_kind == CHANGE_KIND_FIRST_RUN {
        "first run".to_owned()
    } else if facts.change_kind == CHANGE_KIND_RENAMED {
        "rename".to_owned()
    } else if facts.query_changed {
        "query changed with replay_on_change full".to_owned()
    } else if !facts.changed_functions.is_empty() {
        format!(
            "function {} changed with replay_on_change full",
            facts.changed_functions.join(", ")
        )
    } else if facts.has_schema_findings {
        "schema changed with replay_on_change full".to_owned()
    } else {
        "full backfill".to_owned()
    }
}
