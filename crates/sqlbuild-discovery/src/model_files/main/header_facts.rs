//! What a model's native header values show, read as their Python projection reads.

use sqlbuild_model_config::config_presence::main::blocks_config_reuse::blocks_config_reuse;
use sqlbuild_model_config::config_presence::main::contains_template::contains_template;
use sqlbuild_model_config::config_presence::main::entry_macro_path::entry_macro_path;
use sqlbuild_model_config::header_metadata::main::parse_header_metadata::parse_header_metadata;
use sqlbuild_model_config::header_metadata::models::{ParsedAudit, ParsedColumn};
use sqlbuild_model_config::types::{AuthoredNode, NodeKind};
use sqlbuild_sqltext::compiler::models::AuthoredValue;

use crate::model_files::_helpers::native_nodes::{NativeNode, dict_entries, exactly};
use crate::model_files::models::{EntryFacts, HeaderFacts, NativeAudit, NativeColumn};

const COLUMNS_KEY: &str = "columns";

static NULL_VALUE: AuthoredValue = AuthoredValue::Null;

/// The header facts of one model's native authored values; `path` names it in parse messages.
#[must_use]
pub fn header_facts(values: &[(String, AuthoredValue)], path: &str) -> HeaderFacts {
    let entries: Vec<(&str, &AuthoredValue)> = dict_entries(values);
    let facts: Vec<(String, EntryFacts)> = entries
        .iter()
        .map(|&(key, value)| {
            let node: NativeNode<'_> = NativeNode::Value(value);
            (
                key.to_owned(),
                EntryFacts {
                    template: contains_template(&node),
                    macro_path: entry_macro_path(&NativeNode::Key(key), &node),
                    blocks_reuse: blocks_config_reuse(&node),
                },
            )
        })
        .collect();
    let columns: Option<Vec<NativeColumn>> = entries
        .iter()
        .find(|(key, _)| *key == COLUMNS_KEY)
        .map(|&(_, value)| value)
        .filter(|value| **value != AuthoredValue::Null)
        .and_then(|value| {
            let (metadata, exact) = exactly(|| {
                parse_header_metadata(
                    &NativeNode::Value(value),
                    &NativeNode::Value(&NULL_VALUE),
                    path,
                )
            });
            let columns: Vec<ParsedColumn<NativeNode<'_>>> =
                metadata.columns.ok().filter(|_| exact)?;
            Some(columns.iter().map(native_column).collect())
        });
    HeaderFacts {
        entries: facts,
        columns,
    }
}

fn text(node: Option<&NativeNode<'_>>) -> Option<String> {
    node.and_then(AuthoredNode::text)
}

fn flag(node: Option<&NativeNode<'_>>) -> Option<bool> {
    match node.map(AuthoredNode::kind) {
        Some(NodeKind::Bool(value)) => Some(value),
        _ => None,
    }
}

/// A parsed column's leaves as the projected text, flags and counts.
fn native_column(column: &ParsedColumn<NativeNode<'_>>) -> NativeColumn {
    NativeColumn {
        name: column.name.text().unwrap_or_default(),
        column_type: text(column.column_type.as_ref()),
        nullable: flag(column.nullable.as_ref()),
        description: text(column.description.as_ref()),
        audits: column.audits.iter().map(native_audit).collect(),
        migrate_from: text(column.migrate_from.as_ref()),
    }
}

fn native_audit(audit: &ParsedAudit<NativeNode<'_>>) -> NativeAudit {
    NativeAudit {
        definition_name: audit.definition_name.text().unwrap_or_default(),
        arguments: audit
            .arguments
            .iter()
            .map(|(key, value)| (key.text().unwrap_or_default(), value.authored()))
            .collect(),
        name: text(audit.name.as_ref()),
        description: text(audit.description.as_ref()),
        severity: text(audit.severity.as_ref()),
        run_scope: text(audit.run_scope.as_ref()),
        always_run: flag(audit.always_run.as_ref()),
        thresholds: audit.thresholds,
        minimum_samples: audit.minimum_samples.as_ref().map(NativeNode::authored),
        evidence_limit: audit.evidence_limit.as_ref().map(NativeNode::authored),
    }
}
