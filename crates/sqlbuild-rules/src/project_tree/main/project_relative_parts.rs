//! The parts of a path relative to the project and an optional directory inside it.

use std::ffi::OsString;
use std::path::{Path, PathBuf};

use crate::project_tree::_helpers::relative_paths::{part_list, pure_parts, pure_relative_to};
use crate::project_tree::errors::RelativePartsError;
use crate::project_tree::models::PureParts;

/// `path`'s parts, made project-relative through `resolve` when absolute, then relative to `under`.
pub fn project_relative_parts<E>(
    path: &Path,
    root: &Path,
    under: Option<&Path>,
    resolve: impl FnOnce(&Path) -> Result<PathBuf, E>,
) -> Result<Vec<OsString>, RelativePartsError<E>> {
    let mut parts: PureParts = pure_parts(path);
    if path.is_absolute() {
        let resolved: PathBuf = resolve(path).map_err(RelativePartsError::Resolve)?;
        parts = pure_relative_to(&pure_parts(&resolved), &pure_parts(root))
            .ok_or(RelativePartsError::Escapes)?;
    }
    if let Some(under) = under {
        parts =
            pure_relative_to(&parts, &pure_parts(under)).ok_or(RelativePartsError::NotBeneath)?;
    }
    Ok(part_list(parts))
}
