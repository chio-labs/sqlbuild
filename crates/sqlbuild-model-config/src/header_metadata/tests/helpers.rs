use crate::errors::ConfigError;
use crate::header_metadata::main::parse_header_metadata::parse_header_metadata;
use crate::header_metadata::models::{ParsedAudit, ParsedColumn};
use crate::tests::test_types::Value;
use crate::types::AuthoredNode;

/// A mapping from string keys.
pub(super) fn map(entries: &[(&'static str, Value)]) -> Value {
    Value::Map(
        entries
            .iter()
            .map(|(key, value)| (Value::Str(key), value.clone()))
            .collect(),
    )
}

/// The model file path the parse errors name.
pub(super) const MODEL_PATH: &str = "/project/models/orders.sql";

/// The parse as one line per column and model audit, or the first error or `unsupported`.
pub(super) fn summary(columns: &Value, audits: &Value) -> Result<Vec<String>, String> {
    let metadata = parse_header_metadata(columns, audits, MODEL_PATH);
    let columns: Vec<String> = metadata
        .columns
        .map_err(stop_summary)?
        .iter()
        .map(column_summary)
        .collect();
    let audits = metadata.audits.map_err(stop_summary)?;
    Ok(columns
        .into_iter()
        .chain(audits.iter().map(audit_summary))
        .collect())
}

fn stop_summary(stop: ConfigError) -> String {
    stop.message
}

fn column_summary(column: &ParsedColumn<Value>) -> String {
    format!(
        "{} {} {} {}",
        text(Some(&column.name)),
        text(column.column_type.as_ref()),
        column
            .nullable
            .as_ref()
            .map_or("-".to_owned(), |value| format!("{value:?}")),
        column
            .audits
            .iter()
            .map(audit_summary)
            .collect::<Vec<_>>()
            .join(",")
    )
}

fn audit_summary(audit: &ParsedAudit<Value>) -> String {
    let arguments: Vec<String> = audit
        .arguments
        .iter()
        .map(|(key, _)| text(Some(key)))
        .collect();
    format!(
        "{}:{}{}{}",
        text(Some(&audit.definition_name)),
        arguments.join("+"),
        audit
            .severity
            .as_ref()
            .map_or(String::new(), |severity| format!(
                "@{}",
                text(Some(severity))
            )),
        audit.thresholds.map_or(String::new(), |thresholds| format!(
            " warn={:?} error={:?}",
            thresholds.warn, thresholds.error
        ))
    )
}

fn text(value: Option<&Value>) -> String {
    value
        .and_then(AuthoredNode::text)
        .unwrap_or_else(|| "-".to_owned())
}
