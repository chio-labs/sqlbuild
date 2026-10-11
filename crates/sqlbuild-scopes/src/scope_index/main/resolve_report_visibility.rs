//! Python's `_classify_resource` and `_inaccessible_reason` over a full scope lookup.

use std::collections::HashMap;

use crate::scope_index::_helpers::visibility::{inaccessible_reason, visibility_reason};
use crate::scope_index::models::{
    DeclarationIdentity, GrantKind, RejectedPath, ReportLookup, ReportRecords, ResolvedVisibility,
    ResolvedVisible, ResourceRecord, VisibilityReason,
};

/// Every canonical declaration visible to `resource`, by scope or grant, and the rest.
pub fn resolve_report_visibility(
    records: &ReportRecords,
    lookup: &ReportLookup,
    resource: &ResourceRecord,
) -> Result<ResolvedVisibility, RejectedPath> {
    let mut grants: HashMap<&DeclarationIdentity, Vec<usize>> = HashMap::new();
    if let Some(group) = lookup
        .groups
        .grants_by_resource
        .groups
        .iter()
        .find(|group| records.grants[group[0]].resource == resource.identity)
    {
        for grant in group {
            grants
                .entry(&records.grants[*grant].declaration)
                .or_default()
                .push(*grant);
        }
    }
    let mut resolved: ResolvedVisibility = ResolvedVisibility::default();
    for (position, declaration) in lookup.declarations.iter().enumerate() {
        let record = &records.declarations[*declaration];
        let reason: Option<VisibilityReason> = visibility_reason(record, resource)?;
        if let Some(reason) = reason {
            resolved.visible.push(ResolvedVisible {
                position,
                reason,
                grant: None,
            });
        }
        match grants.get(&record.identity) {
            Some(granted) => {
                for grant in granted {
                    resolved.visible.push(ResolvedVisible {
                        position,
                        reason: match records.grants[*grant].kind {
                            GrantKind::TestedMacro => VisibilityReason::TestedMacro,
                            GrantKind::ExpectedModel => VisibilityReason::ExpectedModel,
                        },
                        grant: Some(*grant),
                    });
                }
            }
            None if reason.is_none() => resolved
                .inaccessible
                .push((position, inaccessible_reason(record, resource)?)),
            None => {}
        }
    }
    Ok(resolved)
}
