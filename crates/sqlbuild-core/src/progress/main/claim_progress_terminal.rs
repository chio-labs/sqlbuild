//! Claim the terminal a final resource result reports on.

use crate::progress::_helpers::resources::{
    remove_claimed_terminals, render_resource_terminals, resolve_resource_terminal,
};
use crate::progress::models::ProgressProjection;
use crate::terminal_events::models::TerminalRequest;

/// Claim the targeted or latest terminal; also returns the rows of earlier unclaimed attempts.
#[must_use]
pub fn claim_progress_terminal(
    projection: ProgressProjection,
    request: &TerminalRequest,
) -> (ProgressProjection, Vec<String>, Option<f64>) {
    let Some((resource_id, candidates, target)) = resolve_resource_terminal(&projection, request)
    else {
        return (projection, Vec::new(), None);
    };
    let Some(target_attempt_id) = candidates[target].resource_attempt_id.clone() else {
        return (projection, Vec::new(), None);
    };
    let (mut projection, lines) =
        render_resource_terminals(projection, &candidates[..target], &request.resource_name);
    projection
        .rendered_terminal_ids
        .insert(target_attempt_id.clone());
    let projection: ProgressProjection =
        remove_claimed_terminals(projection, &resource_id, &target_attempt_id);
    (projection, lines, candidates[target].payload.duration_ms)
}
