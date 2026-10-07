//! MODEL column mappings, as `parse_schema_columns` reads them with `migrate_from` allowed.

use std::collections::HashSet;

use crate::header_metadata::_helpers::audits::audit_list;
use crate::header_metadata::_helpers::text::{entry, non_blank_text, optional_bool, optional_text};
use crate::header_metadata::constants::{MODEL_COLUMN_KEYS, NOT_NULL_AUDIT_NAME};
use crate::header_metadata::models::{HeaderMetadataDeferral, ParsedColumn};
use crate::types::{AuthoredNode, NodeKind};

/// Parse an authored columns mapping; Python's `None` declares no columns.
pub(crate) fn column_mapping<N: AuthoredNode>(
    node: &N,
) -> Result<Vec<ParsedColumn<N>>, HeaderMetadataDeferral> {
    match node.kind() {
        NodeKind::Null => Ok(Vec::new()),
        NodeKind::Map => {
            let columns: Vec<ParsedColumn<N>> = node
                .entries()
                .iter()
                .map(|(name, metadata)| column(name, metadata))
                .collect::<Result<_, _>>()?;
            if has_duplicate_names(&columns) {
                Err(HeaderMetadataDeferral::Invalid)
            } else {
                Ok(columns)
            }
        }
        _ => Err(HeaderMetadataDeferral::Invalid),
    }
}

/// Return whether two ASCII column names are equal under Python's `str.lower()`.
fn has_duplicate_names<N: AuthoredNode>(columns: &[ParsedColumn<N>]) -> bool {
    let mut seen: HashSet<String> = HashSet::new();
    !columns.iter().all(|column| {
        column
            .name
            .text()
            .is_some_and(|name| seen.insert(name.to_ascii_lowercase()))
    })
}

fn column<N: AuthoredNode>(
    name: &N,
    metadata: &N,
) -> Result<ParsedColumn<N>, HeaderMetadataDeferral> {
    let text = non_blank_text(name)?;
    if !text.is_ascii() {
        return Err(HeaderMetadataDeferral::Unsupported);
    }
    if metadata.kind() != NodeKind::Map {
        return Err(HeaderMetadataDeferral::Invalid);
    }
    let entries = metadata.entries();
    if !entries.iter().all(|(key, _)| is_column_key(key)) {
        return Err(HeaderMetadataDeferral::Invalid);
    }
    let nullable = optional_bool(entry(&entries, "nullable"))?;
    let audits = match entry(&entries, "audits") {
        Some(value) => audit_list(value)?,
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
        return Err(HeaderMetadataDeferral::Invalid);
    }
    Ok(ParsedColumn {
        name: name.clone(),
        column_type: optional_text(entry(&entries, "type"))?,
        nullable,
        description: optional_text(entry(&entries, "description"))?,
        audits,
        migrate_from: optional_text(entry(&entries, "migrate_from"))?,
    })
}

fn is_column_key<N: AuthoredNode>(key: &N) -> bool {
    MODEL_COLUMN_KEYS.iter().any(|name| key.is_text(name))
}
