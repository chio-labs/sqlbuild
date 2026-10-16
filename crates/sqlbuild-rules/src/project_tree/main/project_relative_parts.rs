//! The parts of a path relative to the project and an optional directory inside it.

use std::ffi::{OsStr, OsString};
use std::os::unix::ffi::OsStrExt;
use std::path::{Path, PathBuf};

use crate::project_tree::_helpers::relative_paths::{is_rooted, relative_parts_to, rooted_parts};
use crate::project_tree::errors::RelativePartsError;

/// `path`'s parts, made project-relative through `resolve` when absolute, then relative to `under`.
pub fn project_relative_parts<E>(
    path: &Path,
    root: &Path,
    under: Option<&Path>,
    resolve: impl FnOnce(&Path) -> Result<PathBuf, E>,
) -> Result<Vec<OsString>, RelativePartsError<E>> {
    let resolved: PathBuf;
    let mut parts: Vec<&[u8]> = rooted_parts(path);
    if is_rooted(&parts) {
        resolved = resolve(path).map_err(RelativePartsError::Resolve)?;
        parts = relative_parts_to(&rooted_parts(&resolved), &rooted_parts(root))
            .ok_or(RelativePartsError::Escapes)?;
    }
    if let Some(under) = under {
        parts = relative_parts_to(&parts, &rooted_parts(under))
            .ok_or(RelativePartsError::NotBeneath)?;
    }
    Ok(parts
        .into_iter()
        .map(|part| OsStr::from_bytes(part).to_os_string())
        .collect())
}
