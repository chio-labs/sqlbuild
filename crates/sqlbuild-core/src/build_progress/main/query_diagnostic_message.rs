//! The diagnostic line of one completed warehouse statement.

use crate::build_progress::models::StatementText;

/// The resource, phase, query identity, status and elapsed time of a statement.
#[must_use]
pub fn query_diagnostic_message(statement: &StatementText) -> String {
    let query_id: &str = match statement.query_id.as_deref() {
        Some(query_id) if !query_id.is_empty() => query_id,
        _ => "query ID unavailable",
    };
    format!(
        "Query  {} {}  phase={}  {query_id}  {}  {:.2}s",
        statement.resource_type,
        statement.resource_name,
        statement.phase,
        statement.status,
        statement.elapsed_seconds
    )
}
