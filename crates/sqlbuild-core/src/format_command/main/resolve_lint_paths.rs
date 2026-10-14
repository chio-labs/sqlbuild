//! Resolve simple path selectors across every formatter-owned SQL folder.

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

use crate::format_command::_helpers::selectors::lint_path_prefixes;
use crate::format_command::_helpers::selectors::matches_path_prefix;
use crate::format_command::_helpers::walk::{as_posix, resolved};
use crate::format_command::main::lint_sql_paths::lint_sql_paths;

/// The selected files, or `None` when a selector needs graph resolution.
#[must_use]
pub fn resolve_lint_paths(
    project_dir: &Path,
    (select, exclude): (&[String], &[String]),
) -> Option<BTreeSet<PathBuf>> {
    let selected_prefixes: Vec<String> = lint_path_prefixes(select)?;
    let excluded_prefixes: Vec<String> = lint_path_prefixes(exclude)?;
    let root: PathBuf = resolved(project_dir);
    Some(
        lint_sql_paths(project_dir, &selected_prefixes)
            .into_iter()
            .filter(|path| {
                path.strip_prefix(&root).is_ok_and(|relative| {
                    !matches_path_prefix(&as_posix(relative), &excluded_prefixes)
                })
            })
            .collect(),
    )
}
