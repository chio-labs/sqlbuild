//! Python's attached generic audit rendering: argument merge, SQL, severity and run scope.

use crate::audits::_helpers::rendering::{merged_arguments, policies, rendered};
use crate::audits::models::{ArgumentValue, AuditAttachment, AuditRendering, RenderedAudit};

/// Render one attachment as Python does, with its errors, or None where Python must decide.
#[must_use]
pub fn render_attached_audit(attachment: &AuditAttachment) -> Option<AuditRendering> {
    if attachment.measurement {
        if attachment.instance_severity.is_some() || !attachment.has_thresholds {
            return None;
        }
    } else if attachment.has_thresholds || attachment.has_minimum_samples {
        return None;
    }
    let arguments: Vec<(String, ArgumentValue)> = match merged_arguments(attachment)? {
        Ok(arguments) => arguments,
        Err(message) => return Some(AuditRendering::Failed(message)),
    };
    let sql_body: String = match rendered(attachment, &attachment.sql_body, &arguments)? {
        Ok(sql) => sql,
        Err(message) => return Some(AuditRendering::Failed(message)),
    };
    let evidence_sql: Option<String> = match &attachment.evidence_sql {
        Some(evidence) => match rendered(attachment, evidence, &arguments)? {
            Ok(sql) => Some(sql),
            Err(message) => return Some(AuditRendering::Failed(message)),
        },
        None => None,
    };
    Some(AuditRendering::Rendered(RenderedAudit {
        sql_body,
        evidence_sql,
        policies: policies(attachment),
    }))
}
