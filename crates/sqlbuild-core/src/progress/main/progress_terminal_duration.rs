//! The duration of the terminal a result would claim, without claiming it.

use crate::progress::_helpers::resources::resolve_resource_terminal;
use crate::progress::models::ProgressProjection;
use crate::terminal_events::models::TerminalRequest;

/// The duration of the terminal `request` selects, leaving its presentation unclaimed.
#[must_use]
pub fn progress_terminal_duration(
    projection: &ProgressProjection,
    request: &TerminalRequest,
) -> Option<f64> {
    let (_, candidates, target) = resolve_resource_terminal(projection, request)?;
    candidates[target].payload.duration_ms
}
