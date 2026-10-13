//! Selection of the terminal a claim takes.

use crate::terminal_events::_helpers::resource_ids::resolved_resource_id;
use crate::terminal_events::models::{TerminalFact, TerminalIndex, TerminalRequest};

/// The pending terminals of the requested resource, in publication order.
pub(crate) fn pending_terminals(index: &TerminalIndex, request: &TerminalRequest) -> Vec<usize> {
    resolved_resource_id(
        index,
        &request.resource_name,
        request.resource_id.as_deref(),
    )
    .and_then(|resolved| index.pending_by_resource_id.get(&resolved).cloned())
    .unwrap_or_default()
}

/// The unclaimed pending terminal the request selects: by attempt, by number, else the latest.
pub(crate) fn claimable_terminal(
    index: &TerminalIndex,
    request: &TerminalRequest,
) -> Option<usize> {
    let facts: &[TerminalFact] = &index.facts;
    let available: Vec<usize> = pending_terminals(index, request)
        .into_iter()
        .filter(|sequence| {
            facts[*sequence]
                .resource_attempt_id
                .as_ref()
                .is_some_and(|attempt| !index.claimed_attempt_ids.contains(attempt))
        })
        .collect();
    if let Some(attempt_id) = &request.resource_attempt_id {
        return available
            .into_iter()
            .find(|sequence| facts[*sequence].resource_attempt_id.as_ref() == Some(attempt_id));
    }
    if let Some(attempt_number) = request.attempt_number {
        return available
            .into_iter()
            .rev()
            .find(|sequence| facts[*sequence].attempt_number == Some(attempt_number));
    }
    available.last().copied()
}
