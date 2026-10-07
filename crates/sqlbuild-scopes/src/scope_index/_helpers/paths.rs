//! Python's scope path normalization and the lexical path relations visibility uses.

use crate::scope_index::constants::{
    CURRENT_PATH_COMPONENT, PARENT_PATH_COMPONENT, PATH_SEPARATOR,
};
use crate::scope_index::models::ScopeDeferral;

/// Python's `normalize_path`; a path Python rejects defers the stage so Python raises its error.
pub(crate) fn normalize_path(display_path: &str) -> Result<String, ScopeDeferral> {
    let raw: String = display_path.replace('\\', "/");
    let has_drive: bool = raw.chars().nth(1) == Some(':');
    if raw.is_empty() || raw.starts_with(PATH_SEPARATOR) || has_drive {
        return Err(deferral(display_path));
    }
    let mut components: Vec<&str> = Vec::new();
    for component in raw.split(PATH_SEPARATOR) {
        if component.is_empty() || component == CURRENT_PATH_COMPONENT {
            continue;
        }
        if component == PARENT_PATH_COMPONENT {
            if components.pop().is_none() {
                return Err(deferral(display_path));
            }
            continue;
        }
        components.push(component);
    }
    if components.is_empty() {
        return Ok(CURRENT_PATH_COMPONENT.to_owned());
    }
    Ok(components.join("/"))
}

/// Python's visibility `_parent`: the normalized folder of `path`, or `.` at the project root.
pub(crate) fn parent(path: &str) -> Result<String, ScopeDeferral> {
    let normalized: String = normalize_path(path)?;
    Ok(match normalized.rfind(PATH_SEPARATOR) {
        Some(index) => normalized[..index].to_owned(),
        None => CURRENT_PATH_COMPONENT.to_owned(),
    })
}

/// Python's `_canonical_ancestors`: every owner whose inherited declarations reach `path`.
pub(crate) fn canonical_ancestors(path: &str) -> Vec<&str> {
    let mut prefixes: Vec<&str> = vec![CURRENT_PATH_COMPONENT];
    for (index, character) in path.char_indices() {
        if character == PATH_SEPARATOR {
            prefixes.push(&path[..index]);
        }
    }
    prefixes.push(path);
    let mut unique: Vec<&str> = Vec::with_capacity(prefixes.len());
    for prefix in prefixes {
        if !unique.contains(&prefix) {
            unique.push(prefix);
        }
    }
    unique
}

/// Python's `_is_canonical_descendant`.
pub(crate) fn is_canonical_descendant(path: &str, ancestor: &str) -> bool {
    ancestor == CURRENT_PATH_COMPONENT
        || path == ancestor
        || path
            .strip_prefix(ancestor)
            .is_some_and(|rest| rest.starts_with(PATH_SEPARATOR))
}

fn deferral(display_path: &str) -> ScopeDeferral {
    ScopeDeferral {
        reason: format!("scope path Python rejects: {display_path}"),
    }
}
