//! Authored column mappings of a MODEL header or SCHEMA declaration, as `parse_schema_columns` reads them.

use std::collections::HashSet;

const MISSING_COLUMNS: &str = "must declare at least one column";

use crate::errors::ConfigError;
use crate::header_metadata::_helpers::audits::audit_list;
use crate::header_metadata::_helpers::text::{
    Site, entry, non_blank_text, optional_bool, optional_text,
};
use crate::header_metadata::constants::{
    MIGRATE_FROM_KEY, MODEL_COLUMN_KEYS, NOT_NULL_AUDIT_NAME, NULLABLE_NOT_NULL_CODE,
};
use crate::header_metadata::models::{ColumnRequest, ParsedColumn};
use crate::types::{AuthoredNode, NodeKind};

/// Parse an authored columns mapping; Python's `None` declares no columns unless they are required.
pub(crate) fn column_mapping<N: AuthoredNode>(
    node: &N,
    request: ColumnRequest<'_>,
) -> Result<Vec<ParsedColumn<N>>, ConfigError> {
    let site = Site {
        path: request.path,
        label: request.label,
        column: None,
    };
    match node.kind() {
        NodeKind::Null if request.require_columns => {
            return Err(site.error(MISSING_COLUMNS));
        }
        NodeKind::Null => return Ok(Vec::new()),
        NodeKind::Map => {}
        _ => return Err(site.error("'columns' must be a mapping")),
    }
    if request.require_columns && node.entries().is_empty() {
        return Err(site.error(MISSING_COLUMNS));
    }
    let mut seen: HashSet<String> = HashSet::new();
    let mut columns: Vec<ParsedColumn<N>> = Vec::new();
    for (name, metadata) in node.entries() {
        let Some(text) = non_blank_text(&name) else {
            return Err(site.error("column names must be non-empty strings"));
        };
        if !seen.insert(text.to_lowercase()) {
            return Err(site.error(&format!(
                "has duplicate column '{text}' (column names are case-insensitive)"
            )));
        }
        columns.push(column(&name, &text, &metadata, request)?);
    }
    Ok(columns)
}

fn column<N: AuthoredNode>(
    name: &N,
    text: &str,
    metadata: &N,
    request: ColumnRequest<'_>,
) -> Result<ParsedColumn<N>, ConfigError> {
    let path: &str = request.path;
    let label = format!("{} column '{text}'", request.label);
    let site = Site {
        path,
        label: &label,
        column: Some(text),
    };
    if metadata.kind() != NodeKind::Map {
        return Err(site.error("metadata must be a mapping"));
    }
    let entries = metadata.entries();
    let unknown = unknown_keys(&entries, request.allow_migrate_from);
    if !unknown.is_empty() {
        return Err(site.error(&format!(
            "has unknown metadata keys: {}",
            unknown.join(", ")
        )));
    }
    let nullable = optional_bool(entry(&entries, "nullable"), site, "nullable")?;
    let audits = match entry(&entries, "audits") {
        Some(value) => audit_list(value, site)?,
        None => Vec::new(),
    };
    let declares_nullable = nullable
        .as_ref()
        .is_some_and(|value| value.kind() == NodeKind::Bool(true));
    if declares_nullable
        && audits
            .iter()
            .any(|audit| audit.definition_name.is_text(NOT_NULL_AUDIT_NAME))
    {
        return Err(ConfigError::compile(format!(
            "{path} column '{text}' cannot set nullable = true and audit not_null"
        ))
        .with_code(NULLABLE_NOT_NULL_CODE)
        .with_help("remove the not_null audit or set nullable = false"));
    }
    Ok(ParsedColumn {
        name: name.clone(),
        column_type: optional_text(entry(&entries, "type"), site, "type")?,
        nullable,
        description: optional_text(entry(&entries, "description"), site, "description")?,
        audits,
        migrate_from: optional_text(entry(&entries, MIGRATE_FROM_KEY), site, MIGRATE_FROM_KEY)?,
    })
}

/// Return the sorted metadata keys a column may not declare; header keys are always strings.
fn unknown_keys<N: AuthoredNode>(entries: &[(N, N)], allow_migrate_from: bool) -> Vec<String> {
    let mut unknown: Vec<String> = entries
        .iter()
        .filter(|(key, _)| {
            !is_model_column_key(key) || (!allow_migrate_from && key.is_text(MIGRATE_FROM_KEY))
        })
        .map(|(key, _)| key.python_str())
        .collect();
    unknown.sort_unstable();
    unknown
}

/// Whether `key` is one of `MODEL_COLUMN_KEYS`.
fn is_model_column_key<N: AuthoredNode>(key: &N) -> bool {
    MODEL_COLUMN_KEYS.iter().any(|name| key.is_text(name))
}
