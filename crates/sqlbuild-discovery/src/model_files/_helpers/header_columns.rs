//! Natively parsed header columns as their projected text, flags and counts.

use sqlbuild_model_config::header_metadata::models::{ParsedAudit, ParsedColumn};
use sqlbuild_model_config::types::{AuthoredNode, NodeKind};
use sqlbuild_sqltext::compiler::models::AuthoredValue;

use crate::model_files::_helpers::native_nodes::NativeNode;
use crate::model_files::models::{NativeAudit, NativeColumn};

pub(crate) const COLUMNS_KEY: &str = "columns";

pub(crate) static NULL_VALUE: AuthoredValue = AuthoredValue::Null;

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
pub(crate) fn native_column(column: &ParsedColumn<NativeNode<'_>>) -> NativeColumn {
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
