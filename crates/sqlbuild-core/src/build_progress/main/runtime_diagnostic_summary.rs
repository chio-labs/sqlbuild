//! The closing lines for scheduler and query diagnostics omitted past their limits.

use crate::build_progress::constants::{QUERY_DIAGNOSTIC_LIMIT, SCHEDULER_DIAGNOSTIC_LIMIT};
use crate::build_progress::main::query_diagnostic_message::query_diagnostic_message;
use crate::build_progress::main::scheduler_diagnostic_message::scheduler_diagnostic_message;
use crate::build_progress::models::{SchedulerStateText, StatementText};

/// One line per diagnostic kind that omitted entries, naming the last omitted one.
#[must_use]
pub fn runtime_diagnostic_summary(
    scheduler: Option<(usize, SchedulerStateText)>,
    query: Option<(usize, &StatementText)>,
) -> Vec<String> {
    let mut lines: Vec<String> = Vec::new();
    if let Some((omitted, state)) = scheduler.filter(|(omitted, _)| *omitted > 0) {
        lines.push(format!(
            "Scheduler diagnostics  {omitted} transitions omitted after {SCHEDULER_DIAGNOSTIC_LIMIT}; final state: {}",
            scheduler_diagnostic_message(state)
        ));
    }
    if let Some((omitted, statement)) = query.filter(|(omitted, _)| *omitted > 0) {
        lines.push(format!(
            "Query diagnostics  {omitted} statements omitted after {QUERY_DIAGNOSTIC_LIMIT} per resource; final query: {}",
            query_diagnostic_message(statement)
        ));
    }
    lines
}
