//! What the finished actions of a janitor run changed.

use crate::janitor_text::constants::DROPPED_ACTION;
use crate::janitor_text::models::{JanitorItemText, JanitorPhase, JanitorResultCounts};

/// Counts of the successful `items`, as the execution result would count them.
#[must_use]
pub fn janitor_item_counts(items: &[JanitorItemText]) -> JanitorResultCounts {
    let mut counts: JanitorResultCounts = JanitorResultCounts::default();
    for item in items.iter().filter(|item| item.error.is_none()) {
        match item.phase {
            JanitorPhase::DeleteRelations => counts.deleted += 1,
            JanitorPhase::Archive => counts.archived += 1,
            JanitorPhase::DeleteArchives => counts.deleted_archives += 1,
            JanitorPhase::DropOldNameViews if item.action == DROPPED_ACTION => {
                counts.dropped_old_name_views += 1;
            }
            JanitorPhase::DropOldNameViews => {}
            JanitorPhase::DropQueryArtifacts => counts.deleted_query_artifacts += 1,
            JanitorPhase::PruneDirectState => counts.pruned_direct_state += 1,
        }
    }
    counts
}
