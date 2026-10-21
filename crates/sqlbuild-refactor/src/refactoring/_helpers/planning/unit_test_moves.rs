//! Unit test files and `TEST` names that follow a renamed or moved model.

use std::collections::BTreeMap;
use std::path::Path;

use crate::refactoring::_helpers::edits::header_edits::test_name_edits;
use crate::refactoring::_helpers::edits::text_edits::{RefactorParts, path_edits};
use crate::refactoring::_helpers::files::paths::{join, name, parent, stem, suffix};
use crate::refactoring::_helpers::files::project_files::ProjectSqlFile;
use crate::refactoring::constants::{
    CURRENT_DIRECTORY, MODELS_ROOT, TEST_FILE_PREFIX, TEST_NAME_SEPARATOR, UNIT_TEST_ROOT,
};
use crate::refactoring::errors::RefactorError;
use crate::refactoring::models::{ManualLocation, UnitTestFacts};
use crate::refactoring::types::UnitTestScopeHost;

/// The model's names and project-relative paths before and after the refactoring.
pub(crate) struct FollowedModel<'a> {
    pub(crate) names: (&'a str, &'a str),
    pub(crate) paths: (&'a str, &'a str),
}

/// Rename `TEST` names of the model's own tests, and move their files when scopes allow.
pub(crate) fn unit_test_parts(
    project_dir: &Path,
    (tests, files): (&[UnitTestFacts], &[ProjectSqlFile]),
    model: &FollowedModel<'_>,
    host: &UnitTestScopeHost<'_>,
) -> Result<RefactorParts, RefactorError> {
    let (old, _) = model.names;
    let mut by_path: BTreeMap<&str, Vec<&UnitTestFacts>> = BTreeMap::new();
    for test in tests {
        by_path.entry(test.path.as_str()).or_default().push(test);
    }
    let mut parts = RefactorParts::default();
    for (path, blocks) in by_path {
        let targets_only_model = |test: &UnitTestFacts| test.target_model_names == [old];
        let owned: Vec<&str> = blocks
            .iter()
            .filter(|test| targets_only_model(test))
            .filter_map(|test| test.name.as_deref())
            .collect();
        if model.names.0 != model.names.1
            && !owned.is_empty()
            && let Some(file) = files.iter().find(|file| file.path == path)
        {
            parts.edits.extend(path_edits(
                path,
                test_name_edits(&file.contents, &file.text, model.names, &owned)?,
            ));
        }
        if !blocks.iter().all(|test| targets_only_model(test)) {
            continue;
        }
        let mut destination = test_destination(path, model);
        if parent(&destination) != parent(path)
            && let Some(reason) = kept_in_folder(path, &destination, host)?
        {
            destination = format!("{}/{}", parent(path), name(&destination));
            parts.notes.push(ManualLocation {
                path: destination.clone(),
                line: None,
                column: None,
                reason,
            });
        }
        if destination == path {
            continue;
        }
        if join(project_dir, &destination).exists()
            || parts
                .moves
                .iter()
                .any(|(_, planned)| *planned == destination)
        {
            parts.blocking.push(ManualLocation {
                path: destination.clone(),
                line: None,
                column: None,
                reason: format!("the unit test {path} must move here, but the file already exists"),
            });
            continue;
        }
        parts.moves.push((path.to_owned(), destination));
    }
    Ok(parts)
}

/// Why the test file at `path` must stay in its folder instead of moving to `destination`.
fn kept_in_folder(
    path: &str,
    destination: &str,
    host: &UnitTestScopeHost<'_>,
) -> Result<Option<String>, RefactorError> {
    let folder = parent(destination);
    Ok(match host(path, destination)? {
        Some(rebound) if rebound.is_empty() => None,
        Some(rebound) => Some(format!(
            "kept in its folder: {} would not resolve to the same declaration from {folder}",
            rebound.join(", ")
        )),
        None => Some(format!(
            "kept in its folder: its declarations could not be checked from {folder}"
        )),
    })
}

/// Where a test file of the model belongs after the refactoring.
fn test_destination(path: &str, model: &FollowedModel<'_>) -> String {
    let (old, new) = model.names;
    let file_stem = stem(path);
    let old_stem = format!("{TEST_FILE_PREFIX}{old}");
    let new_stem = format!("{TEST_FILE_PREFIX}{new}");
    let renamed_stem = match file_stem.strip_prefix(&old_stem) {
        Some("") => new_stem,
        Some(rest) if rest.starts_with(TEST_NAME_SEPARATOR) => format!("{new_stem}{rest}"),
        _ => file_stem.to_owned(),
    };
    let directory = parent(path);
    let mirrored = mirrored_test_directory(model.paths.0)
        .zip(mirrored_test_directory(model.paths.1))
        .filter(|(before, _)| *before == directory)
        .map(|(_, after)| after);
    let directory = mirrored.unwrap_or(directory);
    format!("{directory}/{renamed_stem}{}", suffix(name(path)))
}

/// `tests/unit/<folders>` mirroring a model below `models/<folders>/`, when it has folders.
fn mirrored_test_directory(model_path: &str) -> Option<String> {
    let folders = parent(model_path.strip_prefix(&format!("{MODELS_ROOT}/"))?);
    (folders != CURRENT_DIRECTORY).then(|| format!("{UNIT_TEST_ROOT}/{folders}"))
}
