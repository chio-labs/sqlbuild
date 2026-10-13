//! Resolved SQL files under formatter path prefixes.

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

use crate::format_command::_helpers::walk::{resolved, sql_files_below};
use crate::format_command::constants::{LINT_DIRECTORY_NAMES, SQL_FILE_SUFFIX};

/// Resolved SQL files named by or below `prefixes`, or below every formatter folder when empty.
#[must_use]
pub fn lint_sql_paths(project_dir: &Path, prefixes: &[String]) -> BTreeSet<PathBuf> {
    let roots: Vec<PathBuf> = if prefixes.is_empty() {
        LINT_DIRECTORY_NAMES
            .iter()
            .map(|name| project_dir.join(name))
            .collect()
    } else {
        prefixes
            .iter()
            .map(|prefix| project_dir.join(prefix))
            .collect()
    };
    let mut paths: BTreeSet<PathBuf> = BTreeSet::new();
    for root in roots {
        let is_sql: bool = root.extension().is_some_and(|suffix| {
            format!(".{}", suffix.to_string_lossy()).to_lowercase() == SQL_FILE_SUFFIX
        });
        if root.is_file() && is_sql {
            paths.insert(resolved(&root));
        } else if root.is_dir() {
            paths.extend(sql_files_below(&root).iter().map(|path| resolved(path)));
        }
    }
    paths
}
