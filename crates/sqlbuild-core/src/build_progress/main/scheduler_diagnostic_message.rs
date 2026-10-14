//! The diagnostic line of one concurrent scheduler state transition.

use crate::build_progress::models::SchedulerStateText;

/// Running, ready, waiting and aborted counts against the concurrency limit.
#[must_use]
pub fn scheduler_diagnostic_message(state: SchedulerStateText) -> String {
    let counts: String = format!(
        "Scheduler  {} running, {} ready, {} waiting on dependencies",
        state.running, state.ready, state.waiting
    );
    if state.aborted != 0 {
        return format!(
            "{counts}, {} aborted after stop, limit {}",
            state.aborted, state.limit
        );
    }
    let suffix: &str = if state.running < state.limit && state.ready == 0 && state.waiting > 0 {
        "  (DAG frontier constrained)"
    } else {
        ""
    };
    format!("{counts}, limit {}{suffix}", state.limit)
}
