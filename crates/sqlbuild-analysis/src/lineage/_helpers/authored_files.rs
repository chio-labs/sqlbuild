//! Python's `_authored_files`: `rglob("*")` minus exclusions, sorted as `PurePath` sorts.

use std::fs;
use std::path::{Path, PathBuf};

use crate::lineage::constants::{
    FINGERPRINT_EXCLUDED_PART, FINGERPRINT_EXCLUDED_ROOTS, FINGERPRINT_ROOT_FILES,
    FINGERPRINT_SUFFIXES,
};

/// One hashed file: its path and its project-relative parts.
pub(crate) struct AuthoredFile {
    pub(crate) path: PathBuf,
    pub(crate) parts: Vec<String>,
}

impl AuthoredFile {
    /// `relative_to(project_dir).as_posix()`.
    pub(crate) fn relative_path(&self) -> String {
        self.parts.join("/")
    }

    /// `PurePath.suffix`, lowercased as `str.lower` does.
    pub(crate) fn lower_suffix(&self) -> String {
        python_suffix(self.parts.last().map_or("", String::as_str)).to_lowercase()
    }
}

/// Python's hashed files in its order (links to directories not walked); `None` defers.
pub(crate) fn authored_files(project_dir: &Path) -> Option<Vec<AuthoredFile>> {
    let mut files: Vec<AuthoredFile> = walk(project_dir, &[])?;
    files.sort_by(|left, right| left.parts.cmp(&right.parts));
    Some(files)
}

fn walk(directory: &Path, parts: &[String]) -> Option<Vec<AuthoredFile>> {
    let Ok(entries) = fs::read_dir(directory) else {
        return None;
    };
    let mut files: Vec<AuthoredFile> = Vec::new();
    for entry in entries {
        let Ok(entry) = entry else {
            return None;
        };
        let Ok(name) = entry.file_name().into_string() else {
            return None;
        };
        if is_excluded(parts.is_empty(), &name) {
            continue;
        }
        let Ok(file_type) = entry.file_type() else {
            return None;
        };
        let mut entry_parts: Vec<String> = parts.to_vec();
        entry_parts.push(name);
        let path: PathBuf = entry.path();
        if file_type.is_dir() {
            files.extend(walk(&path, &entry_parts)?);
        } else if entry_parts.last().is_some_and(|name| is_hashed_name(name)) && path.is_file() {
            files.push(AuthoredFile {
                path,
                parts: entry_parts,
            });
        }
    }
    Some(files)
}

fn is_excluded(at_root: bool, name: &str) -> bool {
    name == FINGERPRINT_EXCLUDED_PART || (at_root && FINGERPRINT_EXCLUDED_ROOTS.contains(&name))
}

fn is_hashed_name(name: &str) -> bool {
    FINGERPRINT_ROOT_FILES.contains(&name)
        || FINGERPRINT_SUFFIXES.contains(&python_suffix(name).to_lowercase().as_str())
}

/// `PurePath.suffix`: from the last dot, unless the dot starts or ends the name.
fn python_suffix(name: &str) -> &str {
    match name.rfind('.') {
        Some(index) if index > 0 && index < name.len() - 1 => &name[index..],
        _ => "",
    }
}
