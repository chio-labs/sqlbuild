//! The named declaration kind a project path's folders give a file.

use crate::lint_text::constants::{
    DECLARATION_GROUP_DIRECTORY, GLOBAL_NAMED_ROOT_KINDS, GROUPED_NAMED_ROLE_KINDS,
};

fn starts_with(parts: &[String], prefix: &[&str]) -> bool {
    parts.len() >= prefix.len() && parts.iter().zip(prefix).all(|(part, role)| part == role)
}

/// The `DeclarationKind` value of a global named root or a role under `_sqlbuild`, if any.
#[must_use]
pub fn named_declaration_role_kind(relative_parts: &[String]) -> Option<&'static str> {
    let folders: &[String] = relative_parts
        .split_last()
        .map_or(&[], |(_, folders)| folders);
    if let Some((_, kind)) = GLOBAL_NAMED_ROOT_KINDS
        .iter()
        .find(|(root, _)| starts_with(folders, root))
    {
        return Some(kind);
    }
    for (index, part) in folders.iter().enumerate() {
        if part != DECLARATION_GROUP_DIRECTORY {
            continue;
        }
        if let Some((_, kind)) = GROUPED_NAMED_ROLE_KINDS
            .iter()
            .find(|(role, _)| starts_with(&folders[index + 1..], role))
        {
            return Some(kind);
        }
    }
    None
}
