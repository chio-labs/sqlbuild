//! List the project files a fingerprint covers, in a stable order.

use std::collections::HashSet;
use std::path::{Path, PathBuf};
use walkdir::{DirEntry, WalkDir};

use crate::digest::constants::{
    EXCLUDED_DIRECTORIES, EXCLUDED_ROOT_DIRECTORIES, PRESENCE_ONLY_FILE_SUFFIXES,
};
use crate::digest::errors::FingerprintError;

/// One covered file: its project-relative path, location and whether only presence counts.
pub(crate) struct CoveredFile {
    pub(crate) relative_path: String,
    pub(crate) path: PathBuf,
    pub(crate) presence_only: bool,
}

/// Every file below `root` outside the excluded folders and `excluded_files`, links followed.
pub(crate) fn covered_files(
    root: &Path,
    excluded_files: &HashSet<String>,
) -> Result<Vec<CoveredFile>, FingerprintError> {
    let mut files: Vec<CoveredFile> = Vec::new();
    let walk = WalkDir::new(root)
        .follow_links(true)
        .sort_by_file_name()
        .into_iter()
        .filter_entry(|entry| !excluded_directory(entry));
    for entry in walk {
        let entry: DirEntry = entry.map_err(FingerprintError::Walk)?;
        if !entry.file_type().is_file() {
            continue;
        }
        let relative_path: String = relative_text(root, entry.path())?;
        if excluded_files.contains(&relative_path) {
            continue;
        }
        let presence_only: bool = PRESENCE_ONLY_FILE_SUFFIXES
            .iter()
            .any(|suffix| relative_path.ends_with(suffix));
        files.push(CoveredFile {
            relative_path,
            path: entry.into_path(),
            presence_only,
        });
    }
    Ok(files)
}

fn excluded_directory(entry: &DirEntry) -> bool {
    if !entry.file_type().is_dir() || entry.depth() == 0 {
        return false;
    }
    let Some(name) = entry.file_name().to_str() else {
        return false;
    };
    EXCLUDED_DIRECTORIES.contains(&name)
        || (entry.depth() == 1 && EXCLUDED_ROOT_DIRECTORIES.contains(&name))
}

fn relative_text(root: &Path, path: &Path) -> Result<String, FingerprintError> {
    let relative: &Path = path
        .strip_prefix(root)
        .map_err(|_| FingerprintError::OutsideRoot(path.to_path_buf()))?;
    let non_utf8 = || FingerprintError::NonUtf8Path(path.to_path_buf());
    let parts: Vec<&str> = relative
        .components()
        .map(|component| component.as_os_str().to_str().ok_or_else(non_utf8))
        .collect::<Result<Vec<&str>, FingerprintError>>()?;
    Ok(parts.join("/"))
}
