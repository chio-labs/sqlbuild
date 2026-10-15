//! `diagnostic_severity_problem`: the severity rule of a diagnostic log.

use crate::lifecycle_events::constants::DIAGNOSTIC_SEVERITIES;

/// The rule a diagnostic severity breaks.
#[must_use]
pub fn diagnostic_severity_problem(severity: &str) -> Option<&'static str> {
    (!DIAGNOSTIC_SEVERITIES.contains(&severity))
        .then_some("severity must be one of trace, debug, info, warning, error, critical")
}
