//! Writing formatted files back atomically, in the authored newline convention.

use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use pyo3::exceptions::PyOSError;
use pyo3::prelude::{Bound, PyAny, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};
use rayon::iter::{IntoParallelRefIterator, ParallelIterator};

use crate::bindings::_helpers::format_command::stages::on_format_workers;

const LINE_FEED: &str = "\n";
const CARRIAGE_RETURN_LINE_FEED: &str = "\r\n";

/// One file the formatter would change: its path and its text before and after.
pub(crate) struct FormatChange<'py> {
    pub(crate) path: Bound<'py, PyAny>,
    pub(crate) before: String,
    pub(crate) after: String,
}

/// One file a format run would leave in its final text.
pub(crate) struct PendingWrite<'t> {
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

/// Replace a text file atomically, keeping its permissions; the error names the path.
fn replace_file(path: &Path, contents: &str) -> Result<(), String> {
    let temporary: PathBuf = temporary_path(path);
    let written: std::io::Result<()> = write_replacing(path, &temporary, contents);
    let _ = fs::remove_file(&temporary);
    written.map_err(|error| format!("{}: {error}", path.display()))
}

/// Replace a text file atomically, keeping its permissions.
fn write_atomically(path: &Path, contents: &str) -> PyResult<()> {
    replace_file(path, contents).map_err(PyOSError::new_err)
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

/// The changed files of `writes`, in their order, written in place across the worker threads
/// when `write` is set; a failed write raises the first failure in order.
pub(crate) fn persist_changes<'py>(
    py: Python<'py>,
    writes: &[PendingWrite<'_>],
    write: bool,
) -> PyResult<Vec<FormatChange<'py>>> {
    let changed: Vec<(&Path, String, String)> = writes
        .iter()
        .filter_map(|pending| {
            let after: String = with_newline_style(pending.contents, pending.newline);
            let before: String = with_newline_style(pending.authored, pending.newline);
            (after != before).then_some((pending.path, before, after))
        })
        .collect();
    if write {
        py.detach(|| {
            on_format_workers(|| {
                let written: Vec<Result<(), String>> = changed
                    .par_iter()
                    .map(|(path, _, after)| replace_file(path, after))
                    .collect();
                written.into_iter().collect::<Result<(), String>>()
            })
        })
        .map_err(PyOSError::new_err)?;
    }
    changed
        .into_iter()
        .map(|(path, before, after)| {
            Ok(FormatChange {
                path: path.into_pyobject(py)?.into_any(),
                before,
                after,
            })
        })
        .collect()
}
