//! Authored SQL files as `{Path: str}` dictionaries, and writing formatted files back.

use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use pyo3::exceptions::PyOSError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods};
use pyo3::{pyfunction, wrap_pyfunction};

const LINE_FEED: &str = "\n";
const CARRIAGE_RETURN_LINE_FEED: &str = "\r\n";

/// One file the formatter would change: its path and its text before and after.
pub(crate) struct FormatChange<'py> {
    pub(crate) path: Bound<'py, PyAny>,
    pub(crate) before: String,
    pub(crate) after: String,
}

/// The entries of a `{Path: value}` dictionary, sorted as Python sorts paths.
pub(crate) fn sorted_items<'py>(
    dictionary: &Bound<'py, PyDict>,
) -> PyResult<Vec<(Bound<'py, PyAny>, Bound<'py, PyAny>)>> {
    let mut items: Vec<(PathBuf, Bound<'py, PyAny>, Bound<'py, PyAny>)> = dictionary
        .iter()
        .map(|(key, value)| Ok((key.extract::<PathBuf>()?, key, value)))
        .collect::<PyResult<_>>()?;
    items.sort_by(|left, right| left.0.cmp(&right.0));
    Ok(items
        .into_iter()
        .map(|(_, key, value)| (key, value))
        .collect())
}

/// `{path: overrides.get(path, contents) for path, contents in files.items()}`.
pub(crate) fn overlaid<'py>(
    files: &Bound<'py, PyDict>,
    overrides: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyDict>> {
    let merged: Bound<'py, PyDict> = PyDict::new(files.py());
    for (path, contents) in files.iter() {
        let value: Bound<'py, PyAny> = overrides.get_item(&path)?.unwrap_or(contents);
        merged.set_item(path, value)?;
    }
    Ok(merged)
}

/// Generated contents in the authored newline convention.
fn with_newline_style(contents: &str, newline: &str) -> String {
    let normalized: String = contents.replace(CARRIAGE_RETURN_LINE_FEED, LINE_FEED);
    if newline == LINE_FEED {
        return normalized;
    }
    normalized.replace(LINE_FEED, newline)
}

fn temporary_path(path: &Path) -> PathBuf {
    let name: String = path
        .file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .unwrap_or_default();
    let nanos: u128 = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |elapsed| elapsed.as_nanos());
    path.with_file_name(format!(".{name}.{}{nanos:x}", std::process::id()))
}

fn write_replacing(path: &Path, temporary: &Path, contents: &str) -> std::io::Result<()> {
    let permissions: fs::Permissions = fs::metadata(path)?.permissions();
    let mut handle: File = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(temporary)?;
    handle.set_permissions(permissions)?;
    handle.write_all(contents.as_bytes())?;
    handle.sync_all()?;
    fs::rename(temporary, path)
}

/// Replace a text file atomically, keeping its permissions.
fn write_atomically(path: &Path, contents: &str) -> PyResult<()> {
    let temporary: PathBuf = temporary_path(path);
    let written: std::io::Result<()> = write_replacing(path, &temporary, contents);
    let _ = fs::remove_file(&temporary);
    written.map_err(|error| PyOSError::new_err(format!("{}: {error}", path.display())))
}

/// `write_atomically(*, path, contents)`: replace a text file atomically, keeping its mode.
#[pyfunction]
#[pyo3(name = "write_atomically", signature = (*, path, contents))]
pub(crate) fn write_file_atomically(path: PathBuf, contents: &str) -> PyResult<()> {
    write_atomically(&path, contents)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(write_file_atomically, module)?)
}

/// The changed files in path order, written in place when `write` is set.
pub(crate) fn persist_changes<'py>(
    (files, updated): (&Bound<'py, PyDict>, &Bound<'py, PyDict>),
    newlines: &Bound<'py, PyDict>,
    write: bool,
) -> PyResult<Vec<FormatChange<'py>>> {
    let mut changes: Vec<FormatChange<'py>> = Vec::new();
    for (path, contents) in sorted_items(updated)? {
        let newline: String = newlines
            .get_item(&path)?
            .map_or_else(|| Ok(LINE_FEED.to_owned()), |value| value.extract())?;
        let authored: String = files
            .get_item(&path)?
            .map_or_else(|| Ok(String::new()), |value| value.extract())?;
        let after: String = with_newline_style(&contents.extract::<String>()?, &newline);
        let before: String = with_newline_style(&authored, &newline);
        if after == before {
            continue;
        }
        if write {
            write_atomically(&path.extract::<PathBuf>()?, &after)?;
        }
        changes.push(FormatChange {
            path,
            before,
            after,
        });
    }
    Ok(changes)
}

/// `{Path: contents}` of the collected files, in collection order.
pub(crate) fn file_dictionary<'py>(
    py: Python<'py>,
    files: Vec<(PathBuf, String)>,
) -> PyResult<Bound<'py, PyDict>> {
    let dictionary: Bound<'py, PyDict> = PyDict::new(py);
    for (path, contents) in files {
        dictionary.set_item(path, contents)?;
    }
    Ok(dictionary)
}
