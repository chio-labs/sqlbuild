//! `scan_fixture_null_candidates`: SQL-test fixtures that may hold removable typed nulls.

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

use crate::lint_text::_helpers::fixtures::{fixture_models, in_ignored_directory, sql_files};
use crate::lint_text::constants::UNIT_TEST_ROOT;
use crate::lint_text::errors::LintTextError;
use crate::lint_text::models::FixtureNullCandidates;

/// Resolved `tests/unit` SQL files with typed-null fixtures, optionally only selected ones.
pub fn scan_fixture_null_candidates(
    project_dir: &Path,
    selected_paths: Option<&BTreeSet<PathBuf>>,
) -> Result<FixtureNullCandidates, LintTextError> {
    let root: PathBuf = project_dir.join(UNIT_TEST_ROOT[0]).join(UNIT_TEST_ROOT[1]);
    let mut paths: BTreeSet<String> = BTreeSet::new();
    let mut model_names: BTreeSet<String> = BTreeSet::new();
    for file in sql_files(&root) {
        if in_ignored_directory(&file) {
            continue;
        }
        let Ok(resolved) = file.canonicalize() else {
            continue;
        };
        if selected_paths.is_some_and(|selected| !selected.contains(&resolved)) {
            continue;
        }
        let Ok(contents) = std::fs::read_to_string(&file) else {
            continue;
        };
        if let Some(models) = fixture_models(&contents)? {
            paths.insert(resolved.to_string_lossy().into_owned());
            model_names.extend(models);
        }
    }
    Ok(FixtureNullCandidates {
        paths: paths.into_iter().collect(),
        model_names: model_names.into_iter().collect(),
    })
}
