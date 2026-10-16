//! `compute_log_admits`: whether the compute log retains one record.

use crate::diagnostic_routing::constants::LEVEL_INFO;
use crate::diagnostic_routing::models::RecordFacts;

/// Whether compute logs retain the record; SQL text retention skips SQL records without text.
#[must_use]
pub fn compute_log_admits(record: RecordFacts, include_sql_text: bool) -> bool {
    if !record.internal && record.level < LEVEL_INFO {
        return false;
    }
    let contains_sql: bool = record.has_sql_digest || record.has_sql_text;
    !(include_sql_text && contains_sql && !record.has_sql_text)
}
