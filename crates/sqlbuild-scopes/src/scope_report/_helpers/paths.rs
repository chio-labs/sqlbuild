//! Python's scope path relations, `PurePosixPath` reads and resource path rules of the reports.

use sqlbuild_core::posix_path::main::posix_parts::posix_parts;
use sqlbuild_core::posix_path::main::posix_suffix::posix_suffix;
use sqlbuild_core::text::main::active_python_text::active_python_text;

use crate::scope_index::main::normalize_scope_path::normalize_scope_path;
use crate::scope_index::models::{OwnershipRoot, RejectedPath, ResourceKind};
use crate::scope_report::constants::{
    CURRENT_PATH, INVALID_PATH_TEXT, PATH_SEPARATOR, SQL_SUFFIX, WINDOWS_PATH_SEPARATOR,
    YAML_SUFFIX, YML_SUFFIX,
};

/// Python's `normalize_path`, or the rejection `InvalidScopePathError` reports.
pub(crate) fn normalized(path: &str) -> Result<String, RejectedPath> {
    normalize_scope_path(path).map_err(|failure| RejectedPath {
        failure,
        path: path.to_owned(),
    })
}

/// `safe_scope_path`: the normalized path, without leaking an invalid one.
pub(crate) fn safe_scope_path(path: &str) -> String {
    normalize_scope_path(path).unwrap_or_else(|_| INVALID_PATH_TEXT.to_owned())
}

/// Python's `ancestry` over normalized paths.
pub(crate) fn ancestry(path: &str, ancestor: &str) -> Result<bool, RejectedPath> {
    let path: String = normalized(path)?;
    let ancestor: String = normalized(ancestor)?;
    if ancestor == CURRENT_PATH {
        return Ok(true);
    }
    let path_parts: Vec<&str> = path.split(PATH_SEPARATOR).collect();
    let ancestor_parts: Vec<&str> = ancestor.split(PATH_SEPARATOR).collect();
    Ok(path_parts.len() >= ancestor_parts.len()
        && path_parts[..ancestor_parts.len()] == ancestor_parts[..])
}

/// `len(PurePosixPath(path).parts)`.
pub(crate) fn part_count(path: &str) -> usize {
    posix_parts(path).len()
}

/// `_looks_like_path`: a separator or a `PurePosixPath` suffix.
pub(crate) fn looks_like_path(value: &str) -> bool {
    value.contains(PATH_SEPARATOR)
        || value.contains(WINDOWS_PATH_SEPARATOR)
        || !posix_suffix(active_python_text(), value).is_empty()
}

/// `_default_suffix`: sources are YAML, every other resource SQL.
pub(crate) fn default_suffix(root: &OwnershipRoot) -> &'static str {
    if root.resource_kind == Some(ResourceKind::Source) {
        YML_SUFFIX
    } else {
        SQL_SUFFIX
    }
}

/// `_resource_path_is_valid`: below the root, with the root's authored suffix in any case.
pub(crate) fn resource_path_is_valid(path: &str, root: &OwnershipRoot) -> bool {
    if path == root.path {
        return false;
    }
    let suffix: String = posix_suffix(active_python_text(), path).to_ascii_lowercase();
    if root.resource_kind == Some(ResourceKind::Source) {
        suffix == YML_SUFFIX || suffix == YAML_SUFFIX
    } else {
        suffix == SQL_SUFFIX
    }
}
