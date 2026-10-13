//! POSIX path parts compared, parented and joined the way `PurePosixPath` does.

use crate::rule_results::constants::{CURRENT_DIRECTORY, DECLARATION_GROUP};

/// The parts of a relative POSIX path, without empty or `.` segments.
pub(crate) fn parts(path: &str) -> Vec<String> {
    path.split('/')
        .filter(|part| !part.is_empty() && *part != CURRENT_DIRECTORY)
        .map(str::to_owned)
        .collect()
}

/// `PurePosixPath(*parts).as_posix()`.
pub(crate) fn posix(parts: &[String]) -> String {
    if parts.is_empty() {
        return CURRENT_DIRECTORY.to_owned();
    }
    parts.join("/")
}

/// The folder whose declarations a file sees: above `_sqlbuild/`, else its own folder.
pub(crate) fn owner(path: &[String]) -> Vec<String> {
    match path.iter().position(|part| part == DECLARATION_GROUP) {
        Some(index) => path[..index].to_vec(),
        None => path[..path.len().saturating_sub(1)].to_vec(),
    }
}

/// `os.path.commonpath` of relative folders.
pub(crate) fn common_folder(folders: &[Vec<String>]) -> Vec<String> {
    let (Some(lowest), Some(highest)) = (folders.iter().min(), folders.iter().max()) else {
        return Vec::new();
    };
    lowest
        .iter()
        .zip(highest)
        .take_while(|(left, right)| left == right)
        .map(|(part, _)| part.clone())
        .collect()
}
