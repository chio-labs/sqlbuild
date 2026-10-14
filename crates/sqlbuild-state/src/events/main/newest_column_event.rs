//! `newest_column_event`: the latest recorded rename of either column of a pair.

use crate::events::_helpers::relations::{newest_index, relations_match};
use crate::events::models::{ColumnEventKey, EventRelation};

/// The index of the latest rename on `relation` naming either column; the first wins ties.
#[must_use]
pub fn newest_column_event(
    events: &[ColumnEventKey],
    relation: &EventRelation,
    (origin_column, destination_column): (&str, &str),
) -> Option<usize> {
    let columns: [String; 2] = [
        origin_column.to_lowercase(),
        destination_column.to_lowercase(),
    ];
    newest_index(
        events
            .iter()
            .enumerate()
            .filter(|(_, event)| {
                relations_match(&event.relation, relation)
                    && (columns.contains(&event.origin_column.to_lowercase())
                        || columns.contains(&event.destination_column.to_lowercase()))
            })
            .map(|(index, event)| (index, &event.order)),
    )
}
