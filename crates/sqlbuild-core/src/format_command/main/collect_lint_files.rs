//! Authored SQL files of formatter-owned folders, read without newline translation.

use std::collections::BTreeSet;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use crate::format_command::_helpers::walk::{resolved, sql_files_below};
use crate::format_command::constants::LINT_DIRECTORY_NAMES;

/// Each folder's SQL files in path order, keeping only `selected` resolved paths when given.
pub fn collect_lint_files(
    project_dir: &Path,
    selected: Option<&BTreeSet<PathBuf>>,
) -> io::Result<Vec<(PathBuf, String)>> {
    let mut files: Vec<(PathBuf, String)> = Vec::new();
    for directory_name in LINT_DIRECTORY_NAMES {
        let root: PathBuf = project_dir.join(directory_name);
        if !root.is_dir() {
            continue;
        }
        for file_path in sql_files_below(&root) {
            if selected.is_some_and(|paths| !paths.contains(&resolved(&file_path))) {
                continue;
            }
            let contents: String = fs::read_to_string(&file_path)?;
            files.push((file_path, contents));
        }
    }
    Ok(files)
}
