//! Write, clean and publish compiled artifacts natively for the Python target writer.

use std::collections::HashSet;
use std::path::PathBuf;

use pyo3::exceptions::PyOSError;
use pyo3::prelude::{Bound, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::PyBytes;
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_cache::artifacts::errors::ArtifactError;
use sqlbuild_cache::artifacts::main::publish_staged::publish_staged;
use sqlbuild_cache::artifacts::main::remove_stale::remove_stale;
use sqlbuild_cache::artifacts::main::write_artifacts::write_artifacts;
use sqlbuild_cache::artifacts::models::{Publication, WrittenArtifacts};

use crate::bindings::_helpers::boundary::panics::compiler_guard;

type PublishedRow = (String, Vec<(String, String)>);

/// Write each `(path, contents)` artifact; returns how many were written and left unchanged.
#[pyfunction]
fn write_compiled_artifacts(
    py: Python<'_>,
    files: Vec<(PathBuf, Vec<u8>)>,
    check_existing: bool,
) -> PyResult<(usize, usize)> {
    compiler_guard(|| {
        let outcome: Result<WrittenArtifacts, ArtifactError> =
            py.detach(|| write_artifacts(&files, check_existing));
        let written: WrittenArtifacts = outcome.map_err(|error| artifact_error(py, error))?;
        Ok((written.written, written.unchanged))
    })
}

/// Delete unmanaged compiled files and empty directories; returns how many files were removed.
#[pyfunction]
fn remove_stale_artifacts(
    py: Python<'_>,
    compiled_dir: PathBuf,
    managed: Vec<PathBuf>,
) -> PyResult<usize> {
    compiler_guard(|| {
        let managed: HashSet<PathBuf> = managed.into_iter().collect();
        py.detach(|| remove_stale(&compiled_dir, &managed))
            .map_err(|error| artifact_error(py, error))
    })
}

/// Publish staged artifacts: `("changed", [])`, `("tree", [])` or `("files", [(source, path)])`.
#[pyfunction]
fn publish_staged_artifacts(
    py: Python<'_>,
    staged_dir: PathBuf,
    compiled_dir: PathBuf,
    expected: Vec<PathBuf>,
) -> PyResult<PublishedRow> {
    compiler_guard(|| {
        let expected: HashSet<PathBuf> = expected.into_iter().collect();
        let publication: Publication = py
            .detach(|| publish_staged(&staged_dir, &compiled_dir, &expected))
            .map_err(|error| artifact_error(py, error))?;
        Ok(match publication {
            Publication::StagedChanged => ("changed".to_owned(), Vec::new()),
            Publication::MovedTree => ("tree".to_owned(), Vec::new()),
            Publication::Files(files) => (
                "files".to_owned(),
                files
                    .into_iter()
                    .map(|(source, path)| (lossy(&source), lossy(&path)))
                    .collect(),
            ),
        })
    })
}

fn lossy(path: &std::path::Path) -> String {
    path.to_string_lossy().into_owned()
}

/// The exception Python's writer raises for the same failure.
fn artifact_error(py: Python<'_>, error: ArtifactError) -> PyErr {
    match error {
        ArtifactError::Io { path, error } => match error.raw_os_error() {
            Some(code) => PyOSError::new_err((code, strerror(py, code), lossy(&path))),
            None => PyOSError::new_err(error.to_string()),
        },
        ArtifactError::Move {
            source,
            path,
            error,
        } => match error.raw_os_error() {
            Some(code) => PyOSError::new_err((
                code,
                strerror(py, code),
                lossy(&source),
                py.None(),
                lossy(&path),
            )),
            None => PyOSError::new_err(error.to_string()),
        },
        ArtifactError::ExistingNotUtf8 { path } => existing_decode_error(py, &path),
    }
}

fn strerror(py: Python<'_>, code: i32) -> String {
    py.import("os")
        .and_then(|os| os.call_method1("strerror", (code,)))
        .and_then(|text| text.extract::<String>())
        .unwrap_or_default()
}

/// Decode the existing file in Python so the error is exactly the one `bytes.decode` raises.
fn existing_decode_error(py: Python<'_>, path: &PathBuf) -> PyErr {
    let bytes: Vec<u8> = match std::fs::read(path) {
        Ok(bytes) => bytes,
        Err(error) => return PyOSError::new_err(error.to_string()),
    };
    match PyBytes::new(py, &bytes).call_method1("decode", ("utf-8",)) {
        Err(error) => error,
        Ok(_) => PyOSError::new_err(format!("compiled artifact '{}' changed", path.display())),
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(write_compiled_artifacts, module)?)?;
    module.add_function(wrap_pyfunction!(remove_stale_artifacts, module)?)?;
    module.add_function(wrap_pyfunction!(publish_staged_artifacts, module)?)
}
