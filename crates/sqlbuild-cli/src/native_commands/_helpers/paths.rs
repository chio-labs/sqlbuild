//! `pathlib.Path` construction and `Path.resolve()` over native paths.

use std::path::{Component, Path, PathBuf};

use crate::native_commands::errors::PythonNeeded;
use crate::native_commands::models::ProjectLocation;

/// `Path(text)`: repeated separators, `.` parts and trailing separators dropped.
pub(crate) fn pathlib_path(text: &Path) -> PathBuf {
    let path: PathBuf = text
        .components()
        .filter(|component| *component != Component::CurDir)
        .collect();
    if path.as_os_str().is_empty() {
        return PathBuf::from(".");
    }
    path
}

/// `Path.resolve()`: absolute, with every existing prefix's links followed, as `realpath` does.
pub(crate) fn resolved_path(path: &Path, cwd: &Path) -> PathBuf {
    let absolute: PathBuf = if path.is_absolute() {
        path.to_path_buf()
    } else {
        cwd.join(path)
    };
    if let Ok(real) = std::fs::canonicalize(&absolute) {
        return real;
    }
    let mut resolved: PathBuf = PathBuf::new();
    for component in absolute.components() {
        match component {
            Component::Prefix(_) | Component::RootDir => resolved.push(component.as_os_str()),
            Component::CurDir => {}
            Component::ParentDir => {
                resolved.pop();
            }
            Component::Normal(name) => {
                let candidate: PathBuf = resolved.join(name);
                resolved = std::fs::canonicalize(&candidate).unwrap_or(candidate);
            }
        }
    }
    resolved
}

/// The project directory as given and as `Path.resolve()` reads it.
pub(crate) fn project_location(given: Option<&Path>) -> Result<ProjectLocation, PythonNeeded> {
    let cwd: PathBuf = std::env::current_dir().map_err(|_| PythonNeeded::Installation)?;
    let given: PathBuf = match given {
        Some(raw) => pathlib_path(raw),
        None => cwd.clone(),
    };
    let resolved: PathBuf = resolved_path(&given, &cwd);
    Ok(ProjectLocation { given, resolved })
}
