//! The strongest aggregate terminal for a command's final result document.

use crate::terminal_events::constants::{
    AGGREGATE_OPERATION_NAMES, FAILED_SUFFIX, INVOCATION_TERMINALS, OPERATION_TERMINALS,
    RESOURCE_TERMINALS, RUN_TERMINALS,
};
use crate::terminal_events::models::TerminalIndex;

/// The last invocation, run, aggregate operation, failed resource or resource terminal, in that preference.
#[must_use]
pub fn lifecycle_terminal(index: &TerminalIndex) -> Option<usize> {
    let mut found: [Option<usize>; 5] = [None; 5];
    for (sequence, fact) in index.facts.iter().enumerate() {
        let event_type: &str = fact.event_type.as_str();
        if INVOCATION_TERMINALS.contains(&event_type) {
            found[0] = Some(sequence);
        } else if RUN_TERMINALS.contains(&event_type) {
            found[1] = Some(sequence);
        } else if OPERATION_TERMINALS.contains(&event_type)
            && fact
                .operation_name
                .as_deref()
                .is_some_and(|name| AGGREGATE_OPERATION_NAMES.contains(&name))
        {
            found[2] = Some(sequence);
        } else if RESOURCE_TERMINALS.contains(&event_type) {
            found[4] = Some(sequence);
            if event_type.ends_with(FAILED_SUFFIX) {
                found[3] = Some(sequence);
            }
        }
    }
    found.into_iter().flatten().next()
}
