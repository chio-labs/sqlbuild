//! `Path.rglob("*.sql")` and `Path.resolve()` over formatter-owned folders.

use std::fs;
use std::path::{Path, PathBuf};

use crate::format_command::constants::SQL_FILE_SUFFIX;

/// `path.resolve()`: the canonical path, or the path itself when it cannot be resolved.
pub(crate) fn resolved(path: &Path) -> PathBuf {
    fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf())
}

/// Every `*.sql` file below `root`, without following directory links, sorted as Python sorts paths.
pub(crate) fn sql_files_below(root: &Path) -> Vec<PathBuf> {
    let mut found: Vec<PathBuf> = Vec::new();
    let mut pending: Vec<PathBuf> = vec![root.to_path_buf()];
    while let Some(directory) = pending.pop() {
        let Ok(entries) = fs::read_dir(&directory) else {
            continue;
        };
        for entry in entries.flatten() {
            let path: PathBuf = entry.path();
            let Ok(file_type) = entry.file_type() else {
                continue;
            };
            if file_type.is_dir() {
                pending.push(path);
            } else if entry
                .file_name()
                .to_string_lossy()
                .ends_with(SQL_FILE_SUFFIX)
                && path.is_file()
            {
                found.push(path);
            }
        }
    }
    found.sort();
    found
}

/// `path.as_posix()`.
pub(crate) fn as_posix(path: &Path) -> String {
    path.components()
        .map(|part| part.as_os_str().to_string_lossy().into_owned())
        .collect::<Vec<String>>()
        .join("/")
}
