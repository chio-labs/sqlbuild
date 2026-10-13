//! Render the resource terminals no result callback claimed.

use crate::progress::_helpers::resources::render_resource_terminal;
use crate::progress::models::{ProgressEvent, ProgressProjection};
use crate::terminal_events::constants::RESOURCE_TERMINALS;

/// The rows of every unrendered resource terminal, in first-seen attempt order.
#[must_use]
pub fn close_progress_projection(
    projection: ProgressProjection,
) -> (ProgressProjection, Vec<String>) {
    let terminals: Vec<ProgressEvent> = projection
        .attempt_order
        .iter()
        .filter_map(|attempt_id| projection.attempts_by_id.get(attempt_id))
        .filter(|event| RESOURCE_TERMINALS.contains(&event.event_type.as_str()))
        .cloned()
        .collect();
    let mut projection: ProgressProjection = projection;
    let mut lines: Vec<String> = Vec::new();
    for event in terminals {
        let Some(resource_name) = event.payload.resource_name.clone() else {
            continue;
        };
        let (rendered, line) = render_resource_terminal(projection, &event, &resource_name);
        projection = rendered;
        lines.extend(line);
    }
    (projection, lines)
}
