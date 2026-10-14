//! Translate `sqb format` positional paths into formatter path selectors.

use std::fs;
use std::path::{Path, PathBuf};

use crate::format_command::_helpers::walk::{as_posix, resolved};
use crate::format_command::constants::{
    FORMAT_PATH_CODE, LINT_DIRECTORY_NAMES, PATH_SELECTOR_PREFIX,
};
use crate::format_command::errors::FormatSelectorError;

fn path_error(message: String, help: Option<String>) -> FormatSelectorError {
    FormatSelectorError {
        message,
        code: FORMAT_PATH_CODE,
        help,
    }
}

/// One `path:` selector per positional path, relative to the project root.
pub fn format_path_selectors(
    paths: &[String],
    project_dir: Option<&Path>,
    cwd: &Path,
) -> Result<Vec<String>, FormatSelectorError> {
    let project_root: PathBuf = resolved(project_dir.unwrap_or(cwd));
    let mut selectors: Vec<String> = Vec::new();
    for raw_path in paths {
        let Ok(path) = fs::canonicalize(cwd.join(raw_path)) else {
            return Err(path_error(
                format!("format path '{raw_path}' does not exist"),
                None,
            ));
        };
        let Ok(relative) = path.strip_prefix(&project_root) else {
            return Err(path_error(
                format!(
                    "format path '{raw_path}' is outside the project '{}'",
                    project_root.display()
                ),
                None,
            ));
        };
        let relative: String = as_posix(relative);
        let root: &str = relative.split('/').next().unwrap_or_default();
        if !LINT_DIRECTORY_NAMES.contains(&root) {
            let folders: Vec<String> = LINT_DIRECTORY_NAMES
                .iter()
                .map(|name| format!("{name}/"))
                .collect();
            return Err(path_error(
                format!("format path '{raw_path}' is not under a formatted folder"),
                Some(format!("use a path under {}", folders.join(", "))),
            ));
        }
        selectors.push(format!("{PATH_SELECTOR_PREFIX}{relative}"));
    }
    Ok(selectors)
}
