use crate::header_metadata::main::parse_header_metadata::parse_header_metadata;
use crate::header_metadata::models::{
    HeaderMetadata, HeaderMetadataDeferral, ParsedAudit, ParsedColumn,
};
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

/// The parse as one line per column and model audit, or why Python must parse it.
pub(super) fn summary(
    columns: &Value,
    audits: &Value,
) -> Result<Vec<String>, HeaderMetadataDeferral> {
    parse_header_metadata(columns, audits).map(|metadata| metadata_summary(&metadata))
}

fn metadata_summary(metadata: &HeaderMetadata<Value>) -> Vec<String> {
    metadata
        .columns
        .iter()
        .map(column_summary)
        .chain(metadata.audits.iter().map(audit_summary))
        .collect()
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
        "{}:{}{}",
        text(Some(&audit.definition_name)),
        arguments.join("+"),
        audit
            .severity
            .as_ref()
            .map_or(String::new(), |severity| format!(
                "@{}",
                text(Some(severity))
            ))
    )
}

fn text(value: Option<&Value>) -> String {
    value
        .and_then(AuthoredNode::text)
        .unwrap_or_else(|| "-".to_owned())
}
