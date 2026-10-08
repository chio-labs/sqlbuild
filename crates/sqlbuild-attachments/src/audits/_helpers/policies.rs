//! Python's `resolve_audit_severity` and `resolve_audit_run_scope`, with their errors.

use crate::audits::models::PolicySource;

const SEVERITIES: [&str; 2] = ["warn", "error"];
/// Python lists run scopes sorted.
const RUN_SCOPES: [&str; 2] = ["delta_and_final", "final"];
const SETTINGS_FILE: &str = "sqlbuild_project.toml";

/// The severity text, or Python's error naming the unknown value.
pub(crate) fn resolve_severity(
    instance: Option<&str>,
    default: Option<&str>,
    audit_label: &str,
) -> Result<&'static str, String> {
    match (instance, default) {
        (Some(value), _) => known(&SEVERITIES, value).ok_or_else(|| {
            format!(
                "{audit_label}: unknown severity '{value}'; valid values: {}",
                SEVERITIES.join(", ")
            )
        }),
        (None, Some(value)) => known(&SEVERITIES, value)
            .ok_or_else(|| unknown_setting("default_audit_severity", value, &SEVERITIES)),
        (None, None) => Ok("error"),
    }
}

/// Where the run scope comes from, or Python's error naming the unknown value.
pub(crate) fn resolve_run_scope(
    instance: Option<&str>,
    default: Option<&str>,
) -> Result<PolicySource, String> {
    match (instance, default) {
        (Some(value), _) => known(&RUN_SCOPES, value)
            .map(|_| PolicySource::Instance)
            .ok_or_else(|| {
                format!(
                    "unknown audit run_scope '{value}'; valid values: {}",
                    RUN_SCOPES.join(", ")
                )
            }),
        (None, Some(value)) => known(&RUN_SCOPES, value)
            .map(|_| PolicySource::Default)
            .ok_or_else(|| unknown_setting("default_audit_run_scope", value, &RUN_SCOPES)),
        (None, None) => Ok(PolicySource::Fallback),
    }
}

fn unknown_setting(setting: &str, value: &str, valid: &[&str]) -> String {
    format!(
        "settings.{setting} in {SETTINGS_FILE}: unknown value '{value}'; valid values: {}",
        valid.join(", ")
    )
}

fn known(values: &[&'static str], value: &str) -> Option<&'static str> {
    values.iter().copied().find(|candidate| *candidate == value)
}
