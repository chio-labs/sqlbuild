//! Resolution of one project-relative path to a real, readable project file.

use std::path::{Path, PathBuf};

use crate::project_tree::_helpers::relative_paths::{pure_parts, pure_relative_to};
use crate::project_tree::constants::MISSING_FILE_ERRORS;
use crate::project_tree::errors::ProjectTreeFileError;
use crate::project_tree::main::tracked_text_path::tracked_text_path;
use crate::project_tree::models::PureParts;

/// `root / path` for a relative POSIX path: the root joined with each component.
#[cfg(unix)]
pub(crate) fn joined(root: &Path, parts: &PureParts) -> PathBuf {
    let mut path: PathBuf = root.to_path_buf();
    path.extend(&parts.tail);
    path
}

/// `root / path` as `ntpath.join` builds it, keeping or replacing the root's drive.
#[cfg(not(unix))]
pub(crate) fn joined(root: &Path, parts: &PureParts) -> PathBuf {
    use std::ffi::OsString;
    use std::path::MAIN_SEPARATOR_STR;

    use crate::project_tree::_helpers::relative_paths::same_part;

    let anchor: &str = &parts.anchor.to_string_lossy();
    let drive: &str = anchor.trim_end_matches(MAIN_SEPARATOR_STR);
    let root_anchor: OsString = pure_parts(root).anchor;
    let root_anchor: &str = &root_anchor.to_string_lossy();
    let root_drive: &str = root_anchor.trim_end_matches(MAIN_SEPARATOR_STR);
    let mut path: PathBuf = if drive.len() < anchor.len() {
        let drive: &str = if drive.is_empty() { root_drive } else { drive };
        PathBuf::from(format!("{drive}{MAIN_SEPARATOR_STR}"))
    } else if drive.is_empty() || same_part(drive.as_ref(), root_drive.as_ref()) {
        root.components().collect()
    } else {
        PathBuf::from(drive)
    };
    path.extend(&parts.tail);
    path
}

/// `path.resolve()` of an existing path, spelled without Windows' verbatim `\\?\` prefix.
#[cfg(unix)]
pub(crate) fn real_path(path: &Path) -> std::io::Result<PathBuf> {
    std::fs::canonicalize(path)
}

/// `path.resolve()` of an existing path, spelled without Windows' verbatim `\\?\` prefix.
#[cfg(not(unix))]
pub(crate) fn real_path(path: &Path) -> std::io::Result<PathBuf> {
    use std::ffi::OsString;
    use std::path::{Component, Prefix};

    let real: PathBuf = std::fs::canonicalize(path)?;
    let mut components = real.components();
    let Some(Component::Prefix(prefix)) = components.next() else {
        return Ok(real);
    };
    let anchor: OsString = match prefix.kind() {
        Prefix::VerbatimDisk(drive) => OsString::from(format!("{}:", char::from(drive))),
        Prefix::VerbatimUNC(server, share) => {
            let mut anchor: OsString = OsString::from(r"\\");
            anchor.push(server);
            anchor.push(r"\");
            anchor.push(share);
            anchor
        }
        _ => return Ok(real),
    };
    let mut plain: PathBuf = PathBuf::from(anchor);
    plain.extend(components);
    Ok(plain)
}

/// `path.is_relative_to(root)`, case-folded on Windows as `pathlib` compares there.
pub(crate) fn inside(path: &Path, root: &Path) -> bool {
    if cfg!(unix) {
        path.starts_with(root)
    } else {
        pure_relative_to(&pure_parts(path), &pure_parts(root)).is_some()
    }
}

/// `Path.is_file()`: false for the failures `pathlib` ignores, the failure otherwise.
pub(crate) fn points_to_file(path: &Path) -> Result<bool, ProjectTreeFileError> {
    match std::fs::metadata(path) {
        Ok(metadata) => Ok(metadata.is_file()),
        Err(error) => match error.raw_os_error() {
            Some(errno) if !MISSING_FILE_ERRORS.contains(&errno) => {
                Err(ProjectTreeFileError::Unreadable {
                    path: path.to_path_buf(),
                    errno,
                })
            }
            _ => Ok(false),
        },
    }
}

/// A regular, non-link file under the project's resolved parent directory of the path.
pub(crate) fn regular_file(root: &Path, parts: &PureParts) -> Option<PathBuf> {
    let (name, parent) = parts.tail.split_last()?;
    let parent: PureParts = PureParts {
        anchor: parts.anchor.clone(),
        tail: parent.to_vec(),
    };
    let directory: PathBuf = match real_path(&joined(root, &parent)) {
        Ok(directory) => directory,
        Err(_unresolved) => return None,
    };
    if !inside(&directory, root) {
        return None;
    }
    let candidate: PathBuf = directory.join(name);
    match std::fs::symlink_metadata(&candidate) {
        Ok(metadata) => metadata.file_type().is_file().then_some(candidate),
        Err(_unreadable) => None,
    }
}

/// `candidate` when its lowercased suffix is a tracked text type.
pub(crate) fn tracked(candidate: PathBuf) -> Result<PathBuf, ProjectTreeFileError> {
    if tracked_text_path(&candidate) {
        Ok(candidate)
    } else {
        Err(ProjectTreeFileError::Untracked)
    }
}
