//! `pathlib.Path` construction and `Path.resolve()` over native paths.

use std::path::{Component, Path, PathBuf};

use sqlbuild_rules::project_tree::main::project_real_path::project_real_path;

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
    if absolute.exists() {
        return project_real_path(&absolute);
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
                resolved = if candidate.exists() {
                    project_real_path(&candidate)
                } else {
                    candidate
                };
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
    if !spelled_as_given(&resolved, &cwd.join(&given)) {
        return Err(PythonNeeded::Installation);
    }
    Ok(ProjectLocation { given, resolved })
}

/// Links resolve as in Python on Unix; Windows drive substitutions and mappings stay Python's.
#[cfg(unix)]
fn spelled_as_given(_resolved: &Path, _absolute: &Path) -> bool {
    true
}

/// Whether the resolved path is the absolute path as given, apart from letter case.
#[cfg(not(unix))]
fn spelled_as_given(resolved: &Path, absolute: &Path) -> bool {
    let absolute: PathBuf = absolute
        .components()
        .filter(|component| *component != Component::CurDir)
        .collect();
    resolved
        .to_string_lossy()
        .eq_ignore_ascii_case(&absolute.to_string_lossy())
}
