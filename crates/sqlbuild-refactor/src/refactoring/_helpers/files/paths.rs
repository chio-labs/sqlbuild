//! `pathlib` path semantics the refactoring planner relies on.

use std::path::{Component, Path, PathBuf};

use crate::refactoring::constants::CURRENT_DIRECTORY;

/// Non-strict `Path.resolve()`: symlinks resolve while the path exists, then lexically.
pub(crate) fn resolve(path: &Path) -> PathBuf {
    let mut resolved = PathBuf::new();
    for component in path.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                resolved.pop();
            }
            other => {
                resolved.push(other.as_os_str());
                if let Ok(canonical) = std::fs::canonicalize(&resolved) {
                    resolved = canonical;
                }
            }
        }
    }
    resolved
}

/// A relative path as `PurePath.as_posix()` spells it, or `None` when not relative.
pub(crate) fn relative_posix(path: &Path, base: &Path) -> Option<String> {
    let Ok(relative) = path.strip_prefix(base) else {
        return None;
    };
    let parts: Vec<String> = relative
        .components()
        .map(|component| component.as_os_str().to_string_lossy().into_owned())
        .collect();
    Some(if parts.is_empty() {
        ".".to_owned()
    } else {
        parts.join("/")
    })
}

/// `PurePosixPath(path).name`.
pub(crate) fn name(path: &str) -> &str {
    path.trim_end_matches('/')
        .rsplit('/')
        .next()
        .unwrap_or_default()
}

/// `PurePosixPath(path).parent`, as a string (`.` for a bare name).
pub(crate) fn parent(path: &str) -> String {
    let parts: Vec<&str> = path
        .split('/')
        .filter(|part| !part.is_empty() && *part != CURRENT_DIRECTORY)
        .collect();
    if parts.len() <= 1 {
        return ".".to_owned();
    }
    parts[..parts.len() - 1].join("/")
}

/// `PurePath.suffix`: the final component's last dot suffix, unless the dot starts the name.
pub(crate) fn suffix(name: &str) -> &str {
    match name.rfind('.') {
        Some(index) if index > 0 && index < name.len() - 1 => &name[index..],
        _ => "",
    }
}

/// `PurePosixPath(path).stem`.
pub(crate) fn stem(path: &str) -> &str {
    let name = name(path);
    let suffix = suffix(name);
    &name[..name.len() - suffix.len()]
}

/// `PurePosixPath(path).with_name(name).as_posix()`.
pub(crate) fn with_name(path: &str, new_name: &str) -> String {
    match parent(path).as_str() {
        "." => new_name.to_owned(),
        parent => format!("{parent}/{new_name}"),
    }
}

/// `project_dir / PurePosixPath(relative)`.
pub(crate) fn join(project_dir: &Path, relative: &str) -> PathBuf {
    let mut path = project_dir.to_path_buf();
    for part in relative
        .split('/')
        .filter(|part| !part.is_empty() && *part != CURRENT_DIRECTORY)
    {
        path.push(part);
    }
    path
}
