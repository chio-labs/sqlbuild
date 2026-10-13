//! The latest terminal of a resource, without claiming it.

use crate::terminal_events::_helpers::resource_ids::resolved_resource_id;
use crate::terminal_events::models::TerminalIndex;

/// The sequence of the resource's latest retained terminal.
#[must_use]
pub fn latest_resource_terminal(
    index: &TerminalIndex,
    resource_name: &str,
    resource_id: Option<&str>,
) -> Option<usize> {
    let resolved: String = resolved_resource_id(index, resource_name, resource_id)?;
    index
        .pending_by_resource_id
        .get(&resolved)
        .and_then(|pending| pending.last().copied())
}
