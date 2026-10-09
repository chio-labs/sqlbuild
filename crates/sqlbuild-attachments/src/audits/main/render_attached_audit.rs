//! Attached generic audit rendering: argument merge, SQL, severity and run scope.

use crate::audits::_helpers::rendering::{merged_arguments, policies, rendered};
use crate::audits::models::{ArgumentValue, AuditAttachment, AuditRendering, RenderedAudit};

/// Render one attachment, or the error rendering raises.
#[must_use]
pub fn render_attached_audit(attachment: &AuditAttachment) -> AuditRendering {
    let rendering = || -> Result<RenderedAudit, String> {
        let arguments: Vec<(String, ArgumentValue)> = merged_arguments(attachment)?;
        let sql_body: String = rendered(attachment, &attachment.sql_body, &arguments)?;
        let evidence_sql: Option<String> = attachment
            .evidence_sql
            .as_deref()
            .map(|evidence| rendered(attachment, evidence, &arguments))
            .transpose()?;
        Ok(RenderedAudit {
            sql_body,
            evidence_sql,
            policies: policies(attachment),
        })
    };
    match rendering() {
        Ok(rendered) => AuditRendering::Rendered(rendered),
        Err(message) => AuditRendering::Failed(message),
    }
}
