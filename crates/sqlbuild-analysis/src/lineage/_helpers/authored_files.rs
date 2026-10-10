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

    /// `PurePath.suffix`, lowercased as Python's `str.lower` does.
    pub(crate) fn lower_suffix(&self) -> String {
        python_suffix(self.parts.last().map_or("", String::as_str)).to_lowercase()
    }
}

/// The files Python hashes, in its order, or `None` where Python's own walk must decide.
///
/// `rglob` does not descend into symbolic links to directories, `is_file` follows links, and
/// excluded directories cannot contribute files, so they are not walked.
pub(crate) fn authored_files(project_dir: &Path) -> Option<Vec<AuthoredFile>> {
    let mut files: Vec<AuthoredFile> = Vec::new();
    walk(project_dir, &mut Vec::new(), &mut files)?;
    files.sort_by(|left, right| left.parts.cmp(&right.parts));
    Some(files)
}

fn walk(directory: &Path, parts: &mut Vec<String>, files: &mut Vec<AuthoredFile>) -> Option<()> {
    for entry in fs::read_dir(directory).ok()? {
        let entry = entry.ok()?;
        let name: String = entry.file_name().into_string().ok()?;
        if is_excluded(parts.is_empty(), &name) {
            continue;
        }
        let file_type = entry.file_type().ok()?;
        let path: PathBuf = entry.path();
        if file_type.is_dir() {
            parts.push(name);
            walk(&path, parts, files)?;
            let _ = parts.pop();
            continue;
        }
        if !is_hashed_name(&name) || !path.is_file() {
            continue;
        }
        let mut file_parts: Vec<String> = parts.clone();
        file_parts.push(name);
        files.push(AuthoredFile {
            path,
            parts: file_parts,
        });
    }
    Some(())
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
