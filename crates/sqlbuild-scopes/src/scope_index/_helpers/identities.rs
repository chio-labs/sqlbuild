//! Qualified identity text (`format_identity`) and the `repr` text Python orders lookup keys by.

use crate::scope_index::models::{
    DeclarationIdentity, GrantRecord, GrantThrough, ResourceIdentity, ScopeIndex,
};
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

/// Python's `format_identity` of what a grant came through.
pub(crate) fn grant_through_text(index: &ScopeIndex, grant: &GrantRecord) -> String {
    match &grant.through {
        GrantThrough::Model(name) => format!("model:{name}"),
        GrantThrough::Declaration(declaration) => {
            declaration_text(&index.declarations[*declaration].identity)
        }
    }
}

/// Python's dataclass `repr` of a `ResourceIdentity`.
pub(crate) fn resource_repr(identity: &ResourceIdentity) -> Option<String> {
    Some(format!(
        "ResourceIdentity(kind=<ResourceKind.{}: '{}'>, name={})",
        identity.kind.member_name(),
        identity.kind.as_str(),
        python_str_repr(&identity.name)?
    ))
}

/// Python's dataclass `repr` of a `DeclarationIdentity`.
pub(crate) fn declaration_repr(identity: &DeclarationIdentity) -> Option<String> {
    let owner: String = match &identity.owner {
        None => "None".to_owned(),
        Some(owner) => resource_repr(owner)?,
    };
    Some(format!(
        "DeclarationIdentity(kind=<DeclarationKind.{}: '{}'>, name={}, owner={owner})",
        identity.kind.member_name(),
        identity.kind.as_str(),
        python_str_repr(&identity.name)?
    ))
}
