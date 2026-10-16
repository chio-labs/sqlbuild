//! Project-local cost run artifacts under `target/executions/<run_id>/run.json`.

use std::fs;
use std::path::{Path, PathBuf};

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyResult, Python};
use sqlbuild_core::cost_report::errors::CostArtifactError;
use sqlbuild_core::cost_report::main::check_cost_run_id::check_cost_run_id;
use sqlbuild_core::cost_report::main::cost_artifact_text::cost_artifact_text;
use sqlbuild_core::cost_report::main::order_cost_runs::order_cost_runs;
use sqlbuild_core::cost_report::main::read_cost_artifact::read_cost_artifact;
use sqlbuild_core::cost_report::models::CostRun;

use crate::bindings::_helpers::cost_report::records::artifact_error;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::result_output::integration_values::json_value;

const ARTIFACT_NAME: &str = "run.json";
const TEMPORARY_NAME: &str = ".run.json.tmp";

fn invalid(message: &str) -> CostArtifactError {
    CostArtifactError {
        message: message.to_owned(),
    }
}

/// The directory every run's artifact lives under.
fn executions_root(project_dir: &Path) -> PathBuf {
    project_dir.join("target").join("executions")
}

/// `_run_directory`: the run's directory, which must stay under the executions root.
fn run_directory(project_dir: &Path, run_id: &str) -> Result<PathBuf, CostArtifactError> {
    check_cost_run_id(run_id)?;
    let root: PathBuf = executions_root(project_dir);
    let directory: PathBuf = root.join(run_id);
    if let (Ok(resolved), Ok(resolved_root)) = (directory.canonicalize(), root.canonicalize())
        && !resolved.starts_with(resolved_root)
    {
        return Err(invalid(
            "cost run path must remain under the project execution directory",
        ));
    }
    Ok(directory)
}

/// The run an artifact file describes; I/O failures stay Python `OSError`s.
fn load(py: Python<'_>, path: &Path) -> PyResult<Result<CostRun, CostArtifactError>> {
    let bytes: Vec<u8> = fs::read(path).map_err(PyErr::from)?;
    let Ok(text) = String::from_utf8(bytes) else {
        return Ok(Err(invalid("cost run artifact is not UTF-8 text")));
    };
    let json: Bound<'_, PyModule> = py.import("json")?;
    let payload: Bound<'_, PyAny> = match json.call_method1("loads", (text,)) {
        Ok(payload) => payload,
        Err(error) if error.is_instance(py, &native_field(&json, "JSONDecodeError")?) => {
            return Ok(Err(invalid("cost run artifact is not valid JSON")));
        }
        Err(error) => return Err(error),
    };
    let Some(payload) = json_value(&payload)? else {
        return Ok(Err(invalid("cost run artifact must be an object")));
    };
    Ok(read_cost_artifact(&payload))
}

/// Raise the artifact failure Python reported for the same file.
fn checked<T>(py: Python<'_>, result: Result<T, CostArtifactError>) -> PyResult<T> {
    result.map_err(|error| artifact_error(py, &error))
}

/// `write_cost_run`: atomically replace the run's artifact and return its path.
pub(crate) fn write(py: Python<'_>, project_dir: &Path, run: &CostRun) -> PyResult<PathBuf> {
    let directory: PathBuf = checked(py, run_directory(project_dir, &run.run_id))?;
    fs::create_dir_all(&directory).map_err(PyErr::from)?;
    let destination: PathBuf = directory.join(ARTIFACT_NAME);
    let temporary: PathBuf = directory.join(TEMPORARY_NAME);
    fs::write(&temporary, cost_artifact_text(run)).map_err(PyErr::from)?;
    fs::rename(&temporary, &destination).map_err(PyErr::from)?;
    Ok(destination)
}

/// `read_cost_run`: the run stored under the ID, `None` when it has no artifact.
pub(crate) fn read(py: Python<'_>, project_dir: &Path, run_id: &str) -> PyResult<Option<CostRun>> {
    let path: PathBuf = checked(py, run_directory(project_dir, run_id))?.join(ARTIFACT_NAME);
    if !path.is_file() {
        return Ok(None);
    }
    let run: CostRun = checked(py, load(py, &path)?)?;
    if run.run_id != run_id {
        return Err(artifact_error(
            py,
            &invalid("cost run artifact run ID does not match its directory"),
        ));
    }
    Ok(Some(run))
}

fn listed_run(py: Python<'_>, root: &Path, directory: &Path) -> PyResult<Option<CostRun>> {
    let path: PathBuf = directory.join(ARTIFACT_NAME);
    let (Ok(resolved), Ok(resolved_root)) = (path.canonicalize(), root.canonicalize()) else {
        return Ok(None);
    };
    if !resolved.starts_with(resolved_root) || !path.is_file() {
        return Ok(None);
    }
    let Ok(Ok(run)) = load(py, &path) else {
        return Ok(None);
    };
    let name: Option<&str> = directory.file_name().and_then(|name| name.to_str());
    Ok((name == Some(run.run_id.as_str())).then_some(run))
}

/// `list_cost_runs`: every readable run, newest first; unreadable artifacts are skipped.
pub(crate) fn list(py: Python<'_>, project_dir: &Path) -> PyResult<Vec<CostRun>> {
    let root: PathBuf = executions_root(project_dir);
    let Ok(entries) = fs::read_dir(&root) else {
        return Ok(Vec::new());
    };
    let mut runs: Vec<CostRun> = Vec::new();
    for entry in entries.flatten() {
        if let Some(run) = listed_run(py, &root, &entry.path())? {
            runs.push(run);
        }
    }
    Ok(order_cost_runs(runs))
}
