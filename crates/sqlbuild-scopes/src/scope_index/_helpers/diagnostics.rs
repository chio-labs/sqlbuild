//! The builder's duplicate and naming diagnostics, with Python's exact messages and order.

use crate::scope_index::_helpers::identities::{declaration_text, resource_text};
use crate::scope_index::_helpers::ordering::{declaration_key, group_in_order, resource_key};
use crate::scope_index::models::{
    DeclarationIdentity, DeclarationRecord, ResourceRecord, ScopeDiagnostic,
};
use crate::scope_index::models::{ScopeDiagnosticCode, ScopeKind};
use std::cmp::Ordering;

/// Python's builder diagnostics: resource then declaration diagnostics, sorted together.
pub(crate) fn scope_diagnostics(
    resources: &[ResourceRecord],
    declarations: &[DeclarationRecord],
) -> Vec<ScopeDiagnostic> {
    let mut diagnostics: Vec<ScopeDiagnostic> = resource_diagnostics(resources);
    diagnostics.extend(declaration_diagnostics(declarations));
    diagnostics.sort_by(compare_diagnostics);
    diagnostics
}

fn resource_diagnostics(resources: &[ResourceRecord]) -> Vec<ScopeDiagnostic> {
    let mut diagnostics: Vec<ScopeDiagnostic> = Vec::new();
    let positions: Vec<usize> = (0..resources.len()).collect();
    for group in group_in_order(&positions, |index| resources[index].identity.clone()) {
        if group.len() <= 1 {
            continue;
        }
        let mut sorted: Vec<usize> = group.clone();
        sorted.sort_by_cached_key(|index| resource_key(&resources[*index]));
        let locations: String = sorted
            .iter()
            .map(|index| resources[*index].path.as_str())
            .collect::<Vec<_>>()
            .join(", ");
        for index in group {
            let record: &ResourceRecord = &resources[index];
            diagnostics.push(ScopeDiagnostic {
                code: ScopeDiagnosticCode::DuplicateResource,
                message: format!(
                    "Duplicate resource '{}' at {locations}",
                    resource_text(&record.identity)
                ),
                path: Some(record.path.clone()),
                line: Some(1),
                column: Some(1),
                declaration: None,
                resource: Some(index),
            });
        }
    }
    diagnostics.sort_by(compare_diagnostics);
    diagnostics
}

fn declaration_diagnostics(declarations: &[DeclarationRecord]) -> Vec<ScopeDiagnostic> {
    let mut diagnostics: Vec<ScopeDiagnostic> = Vec::new();
    let mut public: Vec<usize> = Vec::new();
    let mut private: Vec<usize> = Vec::new();
    for (index, record) in declarations.iter().enumerate() {
        if let Some((code, message)) = naming_problem(record) {
            diagnostics.push(declaration_diagnostic(declarations, index, code, message));
        }
        if record.identity.owner.is_none() {
            public.push(index);
        } else {
            private.push(index);
        }
    }
    let public_groups: Vec<Vec<usize>> = group_in_order(&public, |index| {
        let identity: &DeclarationIdentity = &declarations[index].identity;
        (identity.kind, identity.name.clone())
    });
    let private_groups: Vec<Vec<usize>> =
        group_in_order(&private, |index| declarations[index].identity.clone());
    for group in public_groups.into_iter().chain(private_groups) {
        if group.len() <= 1 {
            continue;
        }
        let mut sorted: Vec<usize> = group.clone();
        sorted.sort_by_cached_key(|index| declaration_key(&declarations[*index]));
        let locations: String = sorted
            .iter()
            .map(|index| {
                let item: &DeclarationRecord = &declarations[*index];
                format!("{}:{}:{}", item.path, item.line, item.column)
            })
            .collect::<Vec<_>>()
            .join(", ");
        for index in group {
            let message: String = format!(
                "Duplicate declaration '{}' at {locations}",
                declaration_text(&declarations[index].identity)
            );
            diagnostics.push(declaration_diagnostic(
                declarations,
                index,
                ScopeDiagnosticCode::DuplicateDeclaration,
                message,
            ));
        }
    }
    diagnostics.sort_by(compare_diagnostics);
    diagnostics
}

fn naming_problem(record: &DeclarationRecord) -> Option<(ScopeDiagnosticCode, String)> {
    let name: &str = &record.identity.name;
    if name.starts_with("__") {
        return Some((
            ScopeDiagnosticCode::ReservedDeclarationName,
            format!("Declaration name '{name}' uses reserved '__' prefix"),
        ));
    }
    let private: bool = record.scope == ScopeKind::Private;
    if private && !name.starts_with('_') {
        return Some((
            ScopeDiagnosticCode::InvalidDeclarationName,
            format!("Private declaration name '{name}' must have exactly one leading underscore"),
        ));
    }
    if !private && name.starts_with('_') {
        return Some((
            ScopeDiagnosticCode::InvalidDeclarationName,
            format!("Public declaration name '{name}' must not start with underscore"),
        ));
    }
    None
}

fn declaration_diagnostic(
    declarations: &[DeclarationRecord],
    index: usize,
    code: ScopeDiagnosticCode,
    message: String,
) -> ScopeDiagnostic {
    let record: &DeclarationRecord = &declarations[index];
    ScopeDiagnostic {
        code,
        message,
        path: Some(record.path.clone()),
        line: Some(record.line),
        column: Some(record.column),
        declaration: Some(index),
        resource: None,
    }
}

/// Python's `_diagnostic_key` ordering.
fn compare_diagnostics(left: &ScopeDiagnostic, right: &ScopeDiagnostic) -> Ordering {
    let key = |item: &ScopeDiagnostic| {
        (
            item.path.clone().unwrap_or_default(),
            item.line.unwrap_or(0),
            item.column.unwrap_or(0),
            item.code.as_str(),
        )
    };
    key(left)
        .cmp(&key(right))
        .then_with(|| left.message.cmp(&right.message))
}
