//! Qualified identity text (`format_identity`) and the `repr` text Python orders lookup keys by.

use crate::scope_index::models::{DeclarationIdentity, QualifiedIdentity, ResourceIdentity};
use sqlbuild_core::text::main::active_python_text::active_python_text;
use sqlbuild_core::text::main::python_str_repr::python_str_repr;

/// Python's `format_identity` for a resource.
pub(crate) fn resource_text(identity: &ResourceIdentity) -> String {
    format!("{}:{}", identity.kind.as_str(), identity.name)
}

/// Python's `format_identity` for a declaration.
pub(crate) fn declaration_text(identity: &DeclarationIdentity) -> String {
    match &identity.owner {
        None => format!("{}:{}", identity.kind.as_str(), identity.name),
        Some(owner) => format!(
            "{}:{}:{}.{}",
            identity.kind.as_str(),
            owner.kind.as_str(),
            owner.name,
            identity.name
        ),
    }
}

/// Python's dataclass `repr` of a `ResourceIdentity`.
pub(crate) fn resource_repr(identity: &ResourceIdentity) -> String {
    format!(
        "ResourceIdentity(kind=<ResourceKind.{}: '{}'>, name={})",
        identity.kind.member_name(),
        identity.kind.as_str(),
        python_str_repr(active_python_text(), &identity.name)
    )
}

/// Python's dataclass `repr` of a `DeclarationIdentity`.
pub(crate) fn declaration_repr(identity: &DeclarationIdentity) -> String {
    let owner: String = match &identity.owner {
        None => "None".to_owned(),
        Some(owner) => resource_repr(owner),
    };
    format!(
        "DeclarationIdentity(kind=<DeclarationKind.{}: '{}'>, name={}, owner={owner})",
        identity.kind.member_name(),
        identity.kind.as_str(),
        python_str_repr(active_python_text(), &identity.name)
    )
}

/// Python's `format_identity` of a resource or declaration.
pub(crate) fn qualified_text(identity: &QualifiedIdentity) -> String {
    match identity {
        QualifiedIdentity::Resource(identity) => resource_text(identity),
        QualifiedIdentity::Declaration(identity) => declaration_text(identity),
    }
}

/// Python's dataclass `repr` of a resource or declaration identity.
pub(crate) fn qualified_repr(identity: &QualifiedIdentity) -> String {
    match identity {
        QualifiedIdentity::Resource(identity) => resource_repr(identity),
        QualifiedIdentity::Declaration(identity) => declaration_repr(identity),
    }
}

/// Python's `format_identity` of what a static index grant came through.
#[cfg(test)]
pub(crate) fn grant_through_text(
    index: &crate::scope_index::models::ScopeIndex,
    grant: &crate::scope_index::models::GrantRecord,
) -> String {
    match &grant.through {
        crate::scope_index::models::GrantThrough::Model(name) => format!("model:{name}"),
        crate::scope_index::models::GrantThrough::Declaration(declaration) => {
            declaration_text(&index.declarations[*declaration].identity)
        }
    }
}
