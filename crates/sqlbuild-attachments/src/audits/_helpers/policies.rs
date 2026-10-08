//! Python's `resolve_audit_severity` and `resolve_audit_run_scope`.

use crate::audits::models::PolicySource;

const SEVERITIES: [&str; 2] = ["warn", "error"];
const RUN_SCOPES: [&str; 2] = ["final", "delta_and_final"];

/// The severity text; unknown values defer so Python raises.
pub(crate) fn resolve_severity(
    instance: Option<&str>,
    default: Option<&str>,
) -> Option<&'static str> {
    match (instance, default) {
        (Some(value), _) | (None, Some(value)) => known(&SEVERITIES, value),
        (None, None) => Some("error"),
    }
}

/// Where the run scope comes from; unknown values defer so Python raises.
pub(crate) fn resolve_run_scope(
    instance: Option<&str>,
    default: Option<&str>,
) -> Option<PolicySource> {
    match (instance, default) {
        (Some(value), _) => known(&RUN_SCOPES, value).map(|_| PolicySource::Instance),
        (None, Some(value)) => known(&RUN_SCOPES, value).map(|_| PolicySource::Default),
        (None, None) => Some(PolicySource::Fallback),
    }
}

fn known(values: &[&'static str], value: &str) -> Option<&'static str> {
    values.iter().copied().find(|candidate| *candidate == value)
}
