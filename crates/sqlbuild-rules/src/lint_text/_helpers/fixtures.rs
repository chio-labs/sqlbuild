//! Fixture-null candidate file listing and matching.

use std::path::{Component, Path, PathBuf};
use std::sync::LazyLock;

use regex::Regex;

use crate::lint_text::_helpers::sites::compiled;
use crate::lint_text::constants::{
    FIXTURE_CTE_MARKERS, FIXTURE_TYPED_NULL_PATTERN, IGNORED_SEARCH_DIRECTORIES,
    MODEL_FIXTURE_PATTERN, SQL_SUFFIX,
};
use crate::lint_text::errors::LintTextError;

static TYPED_NULL: LazyLock<Result<Regex, regex::Error>> =
    LazyLock::new(|| Regex::new(FIXTURE_TYPED_NULL_PATTERN));
static MODEL_FIXTURE: LazyLock<Result<Regex, regex::Error>> =
    LazyLock::new(|| Regex::new(MODEL_FIXTURE_PATTERN));

/// Every `*.sql` file below `directory`, without following directory symlinks.
pub(crate) fn sql_files(directory: &Path) -> Vec<PathBuf> {
    let Ok(entries) = std::fs::read_dir(directory) else {
        return Vec::new();
    };
    let mut files: Vec<PathBuf> = Vec::new();
    for entry in entries.flatten() {
        let path: PathBuf = entry.path();
        let is_directory: bool = entry.file_type().is_ok_and(|kind| kind.is_dir());
        if is_directory {
            files.extend(sql_files(&path));
        } else if is_sql_file(&path) {
            files.push(path);
        }
    }
    files
}

fn is_sql_file(path: &Path) -> bool {
    path.file_name()
        .is_some_and(|name| name.to_string_lossy().ends_with(SQL_SUFFIX))
        && path.is_file()
}

/// Whether any path component is a directory the scan never searches.
pub(crate) fn in_ignored_directory(path: &Path) -> bool {
    path.components().any(is_ignored_component)
}

fn is_ignored_component(component: Component<'_>) -> bool {
    match component {
        Component::Normal(part) => IGNORED_SEARCH_DIRECTORIES.contains(&&*part.to_string_lossy()),
        _ => false,
    }
}

/// The models a fixture file stands in for, or `None` when it holds no typed-null fixture.
pub(crate) fn fixture_models(contents: &str) -> Result<Option<Vec<String>>, LintTextError> {
    let folded: String = contents.to_lowercase();
    if !FIXTURE_CTE_MARKERS
        .iter()
        .any(|marker| folded.contains(marker))
        || !compiled(&TYPED_NULL)?.is_match(contents)
    {
        return Ok(None);
    }
    Ok(Some(
        compiled(&MODEL_FIXTURE)?
            .captures_iter(contents)
            .map(|captures| captures["name"].to_string())
            .collect(),
    ))
}
