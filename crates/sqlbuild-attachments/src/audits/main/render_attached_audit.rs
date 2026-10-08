//! Python's attached generic audit rendering: argument merge, SQL, severity and run scope.

use crate::audits::_helpers::parameters::render_parameterized_sql;
use crate::audits::_helpers::policies::{resolve_run_scope, resolve_severity};
use crate::audits::models::{ArgumentValue, AuditAttachment, PolicySource, RenderedAudit};

/// Render one attachment as Python does, or None where Python raises or decides.
#[must_use]
pub fn render_attached_audit(attachment: &AuditAttachment) -> Option<RenderedAudit> {
    if attachment.measurement {
        if attachment.instance_severity.is_some() || !attachment.has_thresholds {
            return None;
        }
    } else if attachment.has_thresholds || attachment.has_minimum_samples {
        return None;
    }
    let arguments: Vec<(String, ArgumentValue)> = merged_arguments(attachment)?;
    let sql_body: String = render_parameterized_sql(&attachment.sql_body, &arguments, false)?;
    let evidence_sql: Option<String> = match &attachment.evidence_sql {
        Some(evidence) => Some(render_parameterized_sql(evidence, &arguments, false)?),
        None => None,
    };
    let severity: &'static str = if attachment.has_thresholds {
        if attachment.threshold_error {
            "error"
        } else {
            "warn"
        }
    } else {
        resolve_severity(
            attachment.instance_severity.as_deref(),
            attachment.default_severity.as_deref(),
        )?
    };
    let run_scope_source: PolicySource = resolve_run_scope(
        attachment.instance_run_scope.as_deref(),
        attachment.default_run_scope.as_deref(),
    )?;
    Some(RenderedAudit {
        sql_body,
        evidence_sql,
        severity,
        run_scope_source,
    })
}

/// Python's `merge_audit_arguments`; values that differ only as Python objects defer.
fn merged_arguments(attachment: &AuditAttachment) -> Option<Vec<(String, ArgumentValue)>> {
    let mut merged: Vec<(String, ArgumentValue)> = attachment.implicit_arguments.clone();
    for (name, value) in &attachment.explicit_arguments {
        match merged.iter_mut().find(|(existing, _)| existing == name) {
            Some((_, existing)) if existing == value => {}
            Some(_) => return None,
            None => merged.push((name.clone(), value.clone())),
        }
    }
    Some(merged)
}
