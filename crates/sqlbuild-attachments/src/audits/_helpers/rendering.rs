//! Python's argument merge, SQL rendering and policy resolution for one attachment.

use crate::audits::_helpers::parameters::{RenderStop, render_parameterized_sql};
use crate::audits::_helpers::policies::{resolve_run_scope, resolve_severity};
use crate::audits::models::{ArgumentValue, AuditAttachment, PolicySource};

/// Severity first, then run scope, as Python resolves them after expanding the SQL.
pub(crate) fn policies(
    attachment: &AuditAttachment,
) -> Result<(&'static str, PolicySource), String> {
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
            &format!(
                "{} audit '{}'",
                attachment.owner_label, attachment.definition_name
            ),
        )?
    };
    let run_scope_source: PolicySource = resolve_run_scope(
        attachment.instance_run_scope.as_deref(),
        attachment.default_run_scope.as_deref(),
    )?;
    Ok((severity, run_scope_source))
}

/// One SQL text rendered, or the missing-argument or unsupported-value error.
pub(crate) fn rendered(
    attachment: &AuditAttachment,
    sql: &str,
    arguments: &[(String, ArgumentValue)],
) -> Result<String, String> {
    render_parameterized_sql(sql, arguments).map_err(|stop| match stop {
        RenderStop::MissingArgument(name) => format!(
            "{} is missing argument '{name}' for generic audit '{}'",
            attachment.owner_label, attachment.definition_name
        ),
        RenderStop::UnsupportedValue(name) => format!(
            "{} generic audit '{}' argument '{name}' uses an unsupported value",
            attachment.owner_label, attachment.definition_name
        ),
    })
}

/// `merge_audit_arguments`: an explicit argument may repeat an implicit one only as equal text.
pub(crate) fn merged_arguments(
    attachment: &AuditAttachment,
) -> Result<Vec<(String, ArgumentValue)>, String> {
    let mut merged: Vec<(String, ArgumentValue)> = attachment
        .implicit_arguments
        .iter()
        .map(|(name, value)| (name.clone(), ArgumentValue::Text(value.clone())))
        .collect();
    for (name, value) in &attachment.explicit_arguments {
        match merged.iter().find(|(existing, _)| existing == name) {
            Some((_, existing)) if existing != value => {
                return Err(format!(
                    "{} audit '{}' must not override implicit {name} from attached context",
                    attachment.owner_label, attachment.definition_name
                ));
            }
            Some(_) => {}
            None => merged.push((name.clone(), value.clone())),
        }
    }
    Ok(merged)
}
