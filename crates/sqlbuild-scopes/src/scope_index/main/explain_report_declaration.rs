//! The scope explanation's standing of one declaration for a resource.

use crate::scope_index::_helpers::identities::qualified_text;
use crate::scope_index::_helpers::visibility::{inaccessible_reason, visibility_reason};
use crate::scope_index::models::{
    DeclarationRecord, DeclarationStanding, GrantKind, RejectedPath, ReportGrant, ReportLookup,
    ReportRecords, ResourceRecord, VisibilityReason,
};

/// Visible by scope, else granted by the resource's relationships, else why it is hidden.
pub fn explain_report_declaration(
    records: &ReportRecords,
    lookup: &ReportLookup,
    resource: &ResourceRecord,
    declaration: &DeclarationRecord,
) -> Result<DeclarationStanding, RejectedPath> {
    if let Some(reason) = visibility_reason(declaration, resource)? {
        return Ok(DeclarationStanding::Visible(reason));
    }
    let mut matching: Vec<&ReportGrant> = Vec::new();
    if let Some(group) = lookup
        .groups
        .grants_by_resource
        .groups
        .iter()
        .find(|group| records.grants[group[0]].resource == resource.identity)
    {
        for grant in group {
            let record: &ReportGrant = &records.grants[*grant];
            if record.declaration == declaration.identity {
                matching.push(record);
            }
        }
    }
    if matching.is_empty() {
        return Ok(DeclarationStanding::Inaccessible(inaccessible_reason(
            declaration,
            resource,
        )?));
    }
    let reason: VisibilityReason = if matching
        .iter()
        .all(|grant| grant.kind == GrantKind::TestedMacro)
    {
        VisibilityReason::TestedMacro
    } else {
        VisibilityReason::ExpectedModel
    };
    let mut through: Vec<String> = matching
        .iter()
        .map(|grant| qualified_text(&grant.through))
        .collect();
    through.sort();
    Ok(DeclarationStanding::Granted(reason, through.join(",")))
}
