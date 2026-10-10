//! Python's `_authored_files`: `sorted(rglob("*"))` minus exclusions, over discovery's snapshot.

use std::path::{Path, PathBuf};

use sqlbuild_discovery::tree::main::interrupted_listings::interrupted_listings;
use sqlbuild_discovery::tree::main::rglob::rglob;
use sqlbuild_discovery::tree::models::{ProjectTree, TreeEntry};

use crate::lineage::constants::{
    FINGERPRINT_EXCLUDED_PART, FINGERPRINT_EXCLUDED_ROOTS, FINGERPRINT_ROOT_FILES,
    FINGERPRINT_SUFFIXES,
};

/// One hashed file: its path and its `as_posix()` project-relative path.
pub(crate) struct AuthoredFile {
    pub(crate) path: PathBuf,
    pub(crate) relative_path: String,
}

impl AuthoredFile {
    /// `PurePath.suffix`, lowercased as `str.lower` does.
    pub(crate) fn lower_suffix(&self) -> String {
        let name = self.relative_path.rsplit('/').next().unwrap_or("");
        python_suffix(name).to_lowercase()
    }
}

/// The files Python hashes, in its order; an undecodable path makes Python's encode fail.
pub(crate) enum AuthoredFiles {
    /// The files, and whether any walked directory's listing failed after it opened.
    Files {
        files: Vec<AuthoredFile>,
        interrupted: bool,
    },
    /// A hashed path whose name is not valid UTF-8 (or UTF-16): Python returns `None`.
    Undecodable,
    /// Discovery's snapshot could not be read; it lists unreadable directories as empty.
    Unavailable,
}

/// `sorted(rglob("*"))`: no links to directories, unreadable directories empty, `PurePath` order.
pub(crate) fn authored_files(project_dir: &Path) -> AuthoredFiles {
    let tree = ProjectTree::new(project_dir);
    let Ok(paths) = rglob(&tree, "", is_hashed_entry) else {
        return AuthoredFiles::Unavailable;
    };
    let mut files: Vec<AuthoredFile> = Vec::new();
    for relative_path in paths {
        if is_excluded(&relative_path) || !tree.absolute(&relative_path).is_file() {
            continue;
        }
        if tree.is_undecodable(&relative_path) {
            return AuthoredFiles::Undecodable;
        }
        files.push(AuthoredFile {
            path: tree.absolute(&relative_path),
            relative_path,
        });
    }
    AuthoredFiles::Files {
        files,
        interrupted: !interrupted_listings(&tree).is_empty(),
    }
}

fn is_hashed_entry(entry: &TreeEntry) -> bool {
    FINGERPRINT_ROOT_FILES.contains(&entry.name.as_str())
        || FINGERPRINT_SUFFIXES.contains(&python_suffix(&entry.name).to_lowercase().as_str())
}

/// `parts[0] in _EXCLUDED_ROOTS` or `"__pycache__" in parts`.
fn is_excluded(relative_path: &str) -> bool {
    let mut parts = relative_path.split('/');
    parts
        .next()
        .is_some_and(|first| FINGERPRINT_EXCLUDED_ROOTS.contains(&first))
        || relative_path
            .split('/')
            .any(|part| part == FINGERPRINT_EXCLUDED_PART)
}

/// `PurePath.suffix`: from the last dot, unless the dot starts or ends the name.
fn python_suffix(name: &str) -> &str {
    match name.rfind('.') {
        Some(index) if index > 0 && index < name.len() - 1 => &name[index..],
        _ => "",
    }
}
