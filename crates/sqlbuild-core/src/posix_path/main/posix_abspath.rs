//! `posixpath.abspath(path)` for a process working directory `cwd`.

use crate::posix_path::constants::{CURRENT, DOUBLE_ROOT, PARENT, ROOT, SEPARATOR};

/// `path` joined to `cwd` when relative, then normalised exactly as `posixpath.normpath` does.
#[must_use]
pub fn posix_abspath(cwd: &str, path: &str) -> String {
    if path.starts_with(SEPARATOR) {
        return posix_normpath(path);
    }
    let joined: String = if cwd.is_empty() || cwd.ends_with(SEPARATOR) {
        format!("{cwd}{path}")
    } else {
        format!("{cwd}{ROOT}{path}")
    };
    posix_normpath(&joined)
}

fn posix_normpath(path: &str) -> String {
    if path.is_empty() {
        return CURRENT.to_owned();
    }
    let root: &str = if path.starts_with(DOUBLE_ROOT) && !path.starts_with("///") {
        DOUBLE_ROOT
    } else if path.starts_with(SEPARATOR) {
        ROOT
    } else {
        ""
    };
    let mut kept: Vec<&str> = Vec::new();
    for part in path.split(SEPARATOR) {
        if part.is_empty() || part == CURRENT {
            continue;
        }
        let keeps_parent: bool =
            (root.is_empty() && kept.is_empty()) || kept.last() == Some(&PARENT);
        if part != PARENT || keeps_parent {
            kept.push(part);
        } else if !kept.is_empty() {
            let _ = kept.pop();
        }
    }
    let normalised: String = format!("{root}{}", kept.join(ROOT));
    if normalised.is_empty() {
        CURRENT.to_owned()
    } else {
        normalised
    }
}
