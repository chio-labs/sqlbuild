//! Python's `query_target`: the resources or declarations a scope query names.

use crate::scope_index::_helpers::paths::checked_path;
use crate::scope_index::main::parse_identity::parse_identity;
use crate::scope_index::models::{
    KeyedGroups, QualifiedIdentity, ReportLookup, ReportRecords, ReportTarget, TargetFailure,
    TargetMatch,
};

/// The group of `groups` whose first member `is_key`, else no members.
fn group_of(groups: &KeyedGroups, is_key: impl Fn(usize) -> bool) -> Vec<usize> {
    groups
        .groups
        .iter()
        .find(|group| is_key(group[0]))
        .cloned()
        .unwrap_or_default()
}

/// The matching records' positions in lookup order, or why Python raises.
pub fn report_target(
    records: &ReportRecords,
    lookup: &ReportLookup,
    target: &ReportTarget,
) -> Result<TargetMatch, TargetFailure> {
    let identity: QualifiedIdentity = match target {
        ReportTarget::Identity(identity) => identity.clone(),
        ReportTarget::Text(text) if text.contains(':') => {
            parse_identity(text).map_err(TargetFailure::Identity)?
        }
        ReportTarget::Text(text) => {
            let path: String = checked_path(text).map_err(TargetFailure::Path)?;
            return Ok(TargetMatch::Resources(group_of(
                &lookup.groups.resources_by_path,
                |resource| matches!(checked_path(&records.resources[resource].path), Ok(found) if found == path),
            )));
        }
    };
    Ok(match identity {
        QualifiedIdentity::Resource(identity) => {
            TargetMatch::Resources(group_of(&lookup.groups.resources, |resource| {
                records.resources[resource].identity == identity
            }))
        }
        QualifiedIdentity::Declaration(identity) => {
            TargetMatch::Declarations(group_of(&lookup.groups.declarations, |declaration| {
                records.declarations[declaration].identity == identity
            }))
        }
    })
}
