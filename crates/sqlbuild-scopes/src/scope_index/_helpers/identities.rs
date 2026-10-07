//! Qualified identity text (`format_identity`) and the `repr` text Python orders lookup keys by.

use crate::scope_index::models::{
    DeclarationIdentity, GrantRecord, GrantThrough, ResourceIdentity, ScopeIndex,
};

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

/// Python's `repr` of a string, or `None` when it holds text whose escaping needs Unicode tables.
pub(crate) fn python_str_repr(value: &str) -> Option<String> {
    if !value.is_ascii() {
        return None;
    }
    let quote: char = if value.contains('\'') && !value.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut text: String = String::with_capacity(value.len() + 2);
    text.push(quote);
    for character in value.chars() {
        match character {
            '\\' => text.push_str("\\\\"),
            '\t' => text.push_str("\\t"),
            '\n' => text.push_str("\\n"),
            '\r' => text.push_str("\\r"),
            _ if character == quote => {
                text.push('\\');
                text.push(character);
            }
            _ if character < ' ' || character == '\x7f' => {
                text.push_str(&format!("\\x{:02x}", u32::from(character)));
            }
            _ => text.push(character),
        }
    }
    text.push(quote);
    Some(text)
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
