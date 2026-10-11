//! The scope report's `_classify`: what one resource sees directly, by relationship, or not.

use std::collections::HashMap;

use crate::scope_index::_helpers::identities::{declaration_text, qualified_text};
use crate::scope_index::_helpers::visibility::{inaccessible_reason, visibility_reason};
use crate::scope_index::models::{
    DeclarationIdentity, GrantKind, RejectedPath, RelationshipEntry, ReportClassification,
    ReportGrant, ReportLookup, ReportRecords, ResourceRecord, ScopeKind, VisibilityReason,
};

/// Each declaration's direct visibility, relationship grants or inaccessible reason.
pub fn classify_report_resource(
    records: &ReportRecords,
    lookup: &ReportLookup,
    resource: &ResourceRecord,
) -> Result<ReportClassification, RejectedPath> {
    let mut granted: HashMap<&DeclarationIdentity, Vec<&ReportGrant>> = HashMap::new();
    if let Some(group) = lookup
        .groups
        .grants_by_resource
        .groups
        .iter()
        .find(|group| records.grants[group[0]].resource == resource.identity)
    {
        for grant in group {
            let record: &ReportGrant = &records.grants[*grant];
            granted.entry(&record.declaration).or_default().push(record);
        }
    }
    let mut classified: ReportClassification = ReportClassification::default();
    for position in &lookup.declarations {
        let declaration = &records.declarations[*position];
        let reason: Option<VisibilityReason> = visibility_reason(declaration, resource)?;
        if let Some(reason) = reason {
            classified.direct.push((*position, reason));
        }
        match granted.get(&declaration.identity) {
            Some(grants) if declaration.scope != ScopeKind::Private => {
                let tested: bool = grants
                    .iter()
                    .all(|grant| grant.kind == GrantKind::TestedMacro);
                let mut through: Vec<String> = grants
                    .iter()
                    .map(|grant| qualified_text(&grant.through))
                    .collect();
                through.sort();
                classified.relationships.push(RelationshipEntry {
                    position: *position,
                    reason: if tested {
                        VisibilityReason::TestedMacro
                    } else {
                        VisibilityReason::ExpectedModel
                    },
                    through: through.join(","),
                });
            }
            _ if reason.is_none() => classified
                .unavailable
                .push((*position, inaccessible_reason(declaration, resource)?)),
            _ => {}
        }
    }
    let key = |position: usize| -> (String, String) {
        let record = &records.declarations[position];
        (declaration_text(&record.identity), record.path.clone())
    };
    classified
        .direct
        .sort_by_cached_key(|(position, _)| key(*position));
    classified
        .relationships
        .sort_by_cached_key(|entry| key(entry.position));
    classified
        .unavailable
        .sort_by_cached_key(|(position, _)| key(*position));
    Ok(classified)
}
