//! The execution-protocol identity of one attached audit.

/// `audit:<name>:<kind>:<target>:<column>`, without empty parts.
#[must_use]
pub fn audit_resource_id(
    audit_name: &str,
    identity_kind: &str,
    (target, column): (Option<&str>, Option<&str>),
) -> String {
    ["audit", audit_name, identity_kind]
        .into_iter()
        .chain(target)
        .chain(column)
        .filter(|part| !part.is_empty())
        .collect::<Vec<&str>>()
        .join(":")
}
