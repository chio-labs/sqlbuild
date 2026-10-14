//! The live aggregate row of concurrently running audits.

use crate::nested_progress::constants::CLEAR_LINE;
use crate::nested_progress::models::AuditAggregate;

/// Running, completed and worker counts on one cleared line.
#[must_use]
pub fn render_audit_aggregate(aggregate: AuditAggregate) -> String {
    format!(
        "{CLEAR_LINE}{CLEAR_LINE}    audit     running {} | completed {}/{} | workers {}",
        aggregate.running, aggregate.completed, aggregate.total, aggregate.workers
    )
}
