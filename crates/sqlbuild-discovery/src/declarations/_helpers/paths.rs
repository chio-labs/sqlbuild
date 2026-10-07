//! Relative path text helpers shared by declaration discovery.

use crate::declarations::models::{DeclarationKind, ScopeKind};

/// The parent of a `/`-separated relative path (`""` at the top).
pub(crate) fn parent(relative_path: &str) -> &str {
    relative_path
        .rsplit_once('/')
        .map_or("", |(parent, _)| parent)
}

/// The final component of a `/`-separated relative path.
pub(crate) fn name(relative_path: &str) -> &str {
    relative_path
        .rsplit_once('/')
        .map_or(relative_path, |(_, name)| name)
}

/// A `/`-separated relative directory joined with one more component.
pub(crate) fn join(directory: &str, name: &str) -> String {
    format!("{directory}/{name}")
}

/// Python's `Path.stem` of a file name.
pub(crate) fn stem(file_name: &str) -> &str {
    match file_name.rfind('.') {
        Some(index) if index > 0 && index + 1 < file_name.len() => &file_name[..index],
        _ => file_name,
    }
}

/// Python's `DECLARATION_DIRECTORY_FACTS` for a scoped declaration directory name.
pub(crate) fn directory_facts(directory_name: &str) -> Option<(DeclarationKind, ScopeKind)> {
    match directory_name {
        "macros" => Some((DeclarationKind::Macro, ScopeKind::Inherited)),
        "enums" => Some((DeclarationKind::Enum, ScopeKind::Inherited)),
        "constants" => Some((DeclarationKind::Constant, ScopeKind::Inherited)),
        "_macros" => Some((DeclarationKind::Macro, ScopeKind::Local)),
        "_enums" => Some((DeclarationKind::Enum, ScopeKind::Local)),
        "_constants" => Some((DeclarationKind::Constant, ScopeKind::Local)),
        _ => None,
    }
}
