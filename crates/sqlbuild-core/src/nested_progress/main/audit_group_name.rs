//! The group an audit result row is listed under.

use crate::build_progress::models::AuditResultText;
use crate::nested_progress::constants::UNATTACHED_GROUP;

/// The attached target, or `(unattached)`.
#[must_use]
pub fn audit_group_name(result: &AuditResultText) -> String {
    match result.attached_target_name.as_deref() {
        Some(target) if !target.is_empty() => target.to_owned(),
        _ => UNATTACHED_GROUP.to_owned(),
    }
}
