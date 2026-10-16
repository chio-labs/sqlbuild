//! `route_admits`: whether a diagnostic destination receives one record.

use crate::diagnostic_routing::constants::LEVEL_INFO;
use crate::diagnostic_routing::models::{RecordFacts, RouteOptions};

/// Whether a destination receives the record; SQL text routes skip digest-only SQL records.
#[must_use]
pub fn route_admits(options: RouteOptions, record: RecordFacts) -> bool {
    if options.internal_only && !record.internal {
        return false;
    }
    if record.internal && !options.allow_internal {
        return false;
    }
    if !record.internal && record.level < LEVEL_INFO {
        return false;
    }
    !(options.include_sql_text && record.has_sql_digest && !record.has_sql_text)
}
