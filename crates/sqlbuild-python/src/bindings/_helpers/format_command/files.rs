//! Writing formatted files back atomically, in the authored newline convention.

use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use pyo3::exceptions::PyOSError;
use pyo3::prelude::{Bound, PyAny, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};

const LINE_FEED: &str = "\n";
const CARRIAGE_RETURN_LINE_FEED: &str = "\r\n";

/// One file the formatter would change: its path and its text before and after.
pub(crate) struct FormatChange<'py> {
    pub(crate) path: Bound<'py, PyAny>,
    /// The run's index of the changed file.
    pub(crate) entry: usize,
    pub(crate) before: String,
    pub(crate) after: String,
}

/// One file a format run would leave in its final text.
pub(crate) struct PendingWrite<'t> {
    pub(crate) entry: usize,
    pub(crate) path: &'t Path,
    /// The text read, or empty for a file the run did not collect.
    pub(crate) authored: &'t str,
    pub(crate) contents: &'t str,
    pub(crate) newline: &'static str,
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

/// The changed files of `writes` in order, written one by one when `write` is set.
pub(crate) fn persist_changes<'py>(
    py: Python<'py>,
    writes: &[PendingWrite<'_>],
    write: bool,
) -> PyResult<Vec<FormatChange<'py>>> {
    let mut changes: Vec<FormatChange<'py>> = Vec::new();
    for pending in writes {
        let after: String = with_newline_style(pending.contents, pending.newline);
        let before: String = with_newline_style(pending.authored, pending.newline);
        if after == before {
            continue;
        }
        if write {
            write_atomically(pending.path, &after)?;
        }
        changes.push(FormatChange {
            path: pending.path.into_pyobject(py)?.into_any(),
            entry: pending.entry,
            before,
            after,
        });
    }
    Ok(changes)
}
