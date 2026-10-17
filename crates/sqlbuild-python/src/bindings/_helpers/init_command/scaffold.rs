//! Create the blank project tree, raising the `OSError` Python's `pathlib` would.

use std::fs::{self, OpenOptions};
use std::io::{self, ErrorKind};
use std::path::Path;

use crate::bindings::_helpers::records::fields::field as native_field;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use sqlbuild_core::constants::PROJECT_CONFIG_FILENAME as PROJECT_FILE;
use sqlbuild_core::init_command::constants::{GITKEEP_FILE, SCAFFOLD_DIRECTORIES};

/// `OSError(errno, strerror, filename)`, which Python narrows to its errno subclass.
fn os_error(py: Python<'_>, error: &io::Error, path: &Path) -> PyErr {
    let raised: PyResult<Bound<'_, PyAny>> = match error.raw_os_error() {
        Some(errno) => {
            let described: String = io::Error::from_raw_os_error(errno).to_string();
            let strerror: &str = described
                .strip_suffix(&format!(" (os error {errno})"))
                .unwrap_or(&described);
            py.import("builtins").and_then(|builtins| {
                native_field(&builtins, "OSError")?.call1((
                    errno,
                    strerror,
                    path.to_string_lossy().into_owned(),
                ))
            })
        }
        None => py
            .import("builtins")
            .and_then(|builtins| native_field(&builtins, "OSError")?.call1((error.to_string(),))),
    };
    match raised {
        Ok(raised) => PyErr::from_value(raised),
        Err(failure) => failure,
    }
}

/// `Path.mkdir(parents=True, exist_ok=True)`.
fn make_directories(path: &Path) -> Result<(), (io::Error, std::path::PathBuf)> {
    match fs::create_dir(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == ErrorKind::NotFound => {
            let Some(parent) = path.parent().filter(|parent| *parent != path) else {
                return Err((error, path.to_path_buf()));
            };
            make_directories(parent)?;
            match fs::create_dir(path) {
                Err(error) if !path.is_dir() => Err((error, path.to_path_buf())),
                _ => Ok(()),
            }
        }
        Err(error) if path.is_dir() => {
            drop(error);
            Ok(())
        }
        Err(error) => Err((error, path.to_path_buf())),
    }
}

/// Create the resource directories, the project file, and `.gitkeep` in empty directories.
pub(crate) fn scaffold_blank_project(
    py: Python<'_>,
    base_dir: &Path,
    project_toml: &str,
) -> PyResult<()> {
    for directory in SCAFFOLD_DIRECTORIES {
        make_directories(&base_dir.join(directory))
            .map_err(|(error, path)| os_error(py, &error, &path))?;
    }
    let project_file = base_dir.join(PROJECT_FILE);
    fs::write(&project_file, project_toml).map_err(|error| os_error(py, &error, &project_file))?;
    for directory in SCAFFOLD_DIRECTORIES {
        let directory = base_dir.join(directory);
        let mut entries =
            fs::read_dir(&directory).map_err(|error| os_error(py, &error, &directory))?;
        if entries.next().is_none() {
            let gitkeep = directory.join(GITKEEP_FILE);
            OpenOptions::new()
                .create(true)
                .append(true)
                .open(&gitkeep)
                .map_err(|error| os_error(py, &error, &gitkeep))?;
        }
    }
    Ok(())
}
