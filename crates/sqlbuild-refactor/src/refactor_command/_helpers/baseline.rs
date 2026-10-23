//! Matching of rule failures before and after a refactoring.

use crate::refactor_command::models::RefactorDiagnostic;
use crate::refactoring::models::FileChange;

/// The index of the first unused earlier failure `matches` accepts.
pub(crate) fn first_unused(
    before: &[RefactorDiagnostic],
    used: &[bool],
    matches: impl Fn(&RefactorDiagnostic) -> bool,
) -> Option<usize> {
    before
        .iter()
        .zip(used)
        .position(|(earlier, used)| !*used && matches(earlier))
}

/// The path a moved file had before the change, or `path` itself.
pub(crate) fn original_path(changes: &[FileChange], path: Option<&str>) -> Option<String> {
    let path: &str = path?;
    let moved: Option<&FileChange> = changes
        .iter()
        .find(|change| change.moved() && change.path == path);
    Some(moved.map_or_else(|| path.to_owned(), |change| change.original_path.clone()))
}

/// The folder of a project-relative POSIX path.
pub(crate) fn parent(path: &str) -> &str {
    path.rsplit_once('/').map_or("", |(parent, _)| parent)
}
