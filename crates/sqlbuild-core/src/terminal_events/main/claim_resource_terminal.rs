//! Claim the terminal a result callback reports on.

use crate::terminal_events::_helpers::claims::{claimable_terminal, pending_terminals};
use crate::terminal_events::models::{TerminalIndex, TerminalRequest};

/// Claim the latest unclaimed matching terminal and retire earlier attempts; also returns its sequence.
#[must_use]
pub fn claim_resource_terminal(
    mut index: TerminalIndex,
    request: &TerminalRequest,
) -> (TerminalIndex, Option<usize>) {
    let Some(target) = claimable_terminal(&index, request) else {
        return (index, None);
    };
    let Some(target_attempt) = index.facts[target].resource_attempt_id.clone() else {
        return (index, None);
    };
    for sequence in pending_terminals(&index, request) {
        if sequence >= target {
            break;
        }
        if let Some(attempt) = index.facts[sequence].resource_attempt_id.clone() {
            index.claimed_attempt_ids.insert(attempt);
        }
    }
    index.claimed_attempt_ids.insert(target_attempt);
    (index, Some(target))
}
