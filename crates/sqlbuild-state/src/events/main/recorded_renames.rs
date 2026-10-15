//! `recorded_renames`: the renames recorded on one relation since a point in time.

use sqlbuild_cursor::algebra::models::LocalDateTime;

use crate::events::_helpers::relations::relations_match;
use crate::events::models::{EventRelation, RecordedRenameKey};

/// Indexes of recorded renames on `relation` created at or after `since`, oldest first.
#[must_use]
pub fn recorded_renames(
    events: &[RecordedRenameKey],
    relation: &EventRelation,
    since: &LocalDateTime,
) -> Vec<usize> {
    let mut indexes: Vec<usize> = events
        .iter()
        .enumerate()
        .filter(|(_, event)| {
            relations_match(relation, &event.relation)
                && event.records_event
                && event.order.created_at >= *since
        })
        .map(|(index, _)| index)
        .collect();
    indexes.sort_by(|left, right| events[*left].order.cmp(&events[*right].order));
    indexes
}
