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

/// One SQL text rendered, Python's missing-argument error, or None to defer.
pub(crate) fn rendered(
    attachment: &AuditAttachment,
    sql: &str,
    arguments: &[(String, ArgumentValue)],
) -> Option<Result<String, String>> {
    match render_parameterized_sql(sql, arguments, false) {
        Ok(rendered) => Some(Ok(rendered)),
        Err(RenderStop::MissingArgument(name)) => Some(Err(format!(
            "{} is missing argument '{name}' for generic audit '{}'",
            attachment.owner_label, attachment.definition_name
        ))),
        Err(RenderStop::UnsupportedValue(name)) => Some(Err(format!(
            "{} generic audit '{}' argument '{name}' uses an unsupported value",
            attachment.owner_label, attachment.definition_name
        ))),
        Err(RenderStop::Deferred) => None,
    }
}

/// Python's `merge_audit_arguments`; None where only Python's `!=` can compare the values.
pub(crate) fn merged_arguments(
    attachment: &AuditAttachment,
) -> Option<Result<Vec<(String, ArgumentValue)>, String>> {
    let mut merged: Vec<(String, ArgumentValue)> = attachment.implicit_arguments.clone();
    for (name, value) in &attachment.explicit_arguments {
        match merged.iter_mut().find(|(existing, _)| existing == name) {
            Some((_, existing)) => {
                if python_unequal(existing, value)? {
                    return Some(Err(format!(
                        "{} audit '{}' must not override implicit {name} from attached context",
                        attachment.owner_label, attachment.definition_name
                    )));
                }
            }
            None => merged.push((name.clone(), value.clone())),
        }
    }
    Some(Ok(merged))
}

/// Python's `left != right`, or None for opaque values and numbers differing only in text.
fn python_unequal(left: &ArgumentValue, right: &ArgumentValue) -> Option<bool> {
    if matches!(left, ArgumentValue::Opaque) || matches!(right, ArgumentValue::Opaque) {
        return None;
    }
    if left == right {
        return Some(false);
    }
    match (left, right) {
        (ArgumentValue::List(left), ArgumentValue::List(right)) => {
            if left.len() != right.len() {
                return Some(true);
            }
            let mut undecided: bool = false;
            for (left, right) in left.iter().zip(right) {
                match python_unequal(left, right) {
                    Some(true) => return Some(true),
                    Some(false) => {}
                    None => undecided = true,
                }
            }
            if undecided { None } else { Some(false) }
        }
        (
            ArgumentValue::Number(_) | ArgumentValue::Boolean(_),
            ArgumentValue::Number(_) | ArgumentValue::Boolean(_),
        ) if !matches!(
            (left, right),
            (ArgumentValue::Boolean(_), ArgumentValue::Boolean(_))
        ) =>
        {
            None
        }
        _ => Some(true),
    }
}
