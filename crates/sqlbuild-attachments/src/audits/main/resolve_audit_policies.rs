//! `resolve_audit_severity` then `resolve_audit_run_scope`, with Python's errors.

use crate::audits::_helpers::policies::{resolve_run_scope, resolve_severity};
use crate::audits::constants::FALLBACK_RUN_SCOPE;
use crate::audits::models::PolicySource;

/// `(severity, run scope)`, or the first error resolving them.
pub fn resolve_audit_policies(
    severity: (Option<&str>, Option<&str>, &str),
    run_scope: (Option<&str>, Option<&str>),
) -> Result<(&'static str, String), String> {
    let (instance_severity, default_severity, audit_label) = severity;
    let severity: &'static str =
        resolve_severity(instance_severity, default_severity, audit_label)?;
    let (instance, default) = run_scope;
    let run_scope: String = match resolve_run_scope(instance, default)? {
        PolicySource::Instance => instance.unwrap_or_default().to_owned(),
        PolicySource::Default => default.unwrap_or_default().to_owned(),
        PolicySource::Fallback => FALLBACK_RUN_SCOPE.to_owned(),
    };
    Ok((severity, run_scope))
}
