//! `newest_move_event`: the latest recorded move naming one relation.

use crate::events::_helpers::relations::{newest_index, relations_match};
use crate::events::models::{EventRelation, MoveEventKey};

/// The index of the latest move naming `relation` as origin or destination; the first wins ties.
#[must_use]
pub fn newest_move_event(events: &[MoveEventKey], relation: &EventRelation) -> Option<usize> {
    newest_index(
        events
            .iter()
            .enumerate()
            .filter(|(_, event)| {
                relations_match(&event.origin, relation)
                    || relations_match(&event.destination, relation)
            })
            .map(|(index, event)| (index, &event.order)),
    )
}
