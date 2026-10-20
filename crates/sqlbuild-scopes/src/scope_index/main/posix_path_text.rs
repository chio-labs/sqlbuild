//! A `/`-separated path as Python's `Path.as_posix` prints it.

use crate::scope_index::constants::{CURRENT_PATH_COMPONENT, PATH_SEPARATOR};

/// `Path(path).as_posix()`: empty and `.` components dropped.
#[must_use]
pub fn posix_path_text(path: &str) -> String {
    let absolute: bool = path.starts_with(PATH_SEPARATOR);
    let parts: Vec<&str> = path
        .split(PATH_SEPARATOR)
        .filter(|part| !part.is_empty() && *part != CURRENT_PATH_COMPONENT)
        .collect();
    match (absolute, parts.is_empty()) {
        (true, _) => format!("{PATH_SEPARATOR}{}", parts.join("/")),
        (false, true) => CURRENT_PATH_COMPONENT.to_owned(),
        (false, false) => parts.join("/"),
    }
}
