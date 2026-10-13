//! Retain one lifecycle fact in publication order.

use crate::terminal_events::constants::RESOURCE_TERMINALS;
use crate::terminal_events::models::{TerminalFact, TerminalIndex};

/// Store a fact once; also returns its sequence, or `None` when the event was already retained.
#[must_use]
pub fn consume_terminal_fact(
    mut index: TerminalIndex,
    fact: TerminalFact,
) -> (TerminalIndex, Option<usize>) {
    if index.sequence_by_event_id.contains_key(&fact.event_id) {
        return (index, None);
    }
    let sequence: usize = index.facts.len();
    index
        .sequence_by_event_id
        .insert(fact.event_id.clone(), sequence);
    if RESOURCE_TERMINALS.contains(&fact.event_type.as_str())
        && let (Some(resource_id), Some(resource_name)) = (&fact.resource_id, &fact.resource_name)
    {
        let ids: &mut Vec<String> = index
            .resource_ids_by_name
            .entry(resource_name.clone())
            .or_default();
        if !ids.contains(resource_id) {
            ids.push(resource_id.clone());
        }
        index
            .pending_by_resource_id
            .entry(resource_id.clone())
            .or_default()
            .push(sequence);
    }
    index.facts.push(fact);
    (index, Some(sequence))
}
