//! `diagnostic_version_problem`: the schema version rule of a diagnostic log.

use crate::lifecycle_events::constants::CURRENT_DIAGNOSTIC_LOG_SCHEMA_VERSION;

/// The rule a diagnostic log's schema version breaks.
#[must_use]
pub fn diagnostic_version_problem(schema_version: i128) -> Option<String> {
    (schema_version != i128::from(CURRENT_DIAGNOSTIC_LOG_SCHEMA_VERSION)).then(|| {
        format!("diagnostic schema_version must be {CURRENT_DIAGNOSTIC_LOG_SCHEMA_VERSION}")
    })
}
