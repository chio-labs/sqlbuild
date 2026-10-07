//! Native discovery results as the plain data the Python discovery facade materialises.

use pyo3::prelude::{Bound, IntoPyObject, Py, PyAny, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::PyTuple;
use pyo3::{IntoPyObjectExt, pyfunction, wrap_pyfunction};
use sqlbuild_discovery::model_files::main::discover_model_files::discover_model_files as discover_models;
use sqlbuild_discovery::model_files::models::{DiscoveredModelFile, ModelFileOptions};
use sqlbuild_discovery::models::{
    DiscoveredFile, FileOutcome, LineColumnSpan, ProjectRoot, StageDeferral,
};
use sqlbuild_discovery::tree::models::ProjectTree;
use std::path::PathBuf;

use crate::bindings::_helpers::functions::map_to_python;
use crate::bindings::models::ModelDiscoveryRequest;
use crate::bindings::types::CompilerDetach;

type PyObject = Py<PyAny>;
type Located = (String, usize, usize, usize, usize);

fn located(locations: Vec<(String, LineColumnSpan)>) -> Vec<Located> {
    locations
        .into_iter()
        .map(|(name, span)| (name, span.line, span.column, span.end_line, span.end_column))
        .collect()
}

fn tuple_object<'py>(py: Python<'py>, items: Vec<PyObject>) -> PyResult<PyObject> {
    Ok(PyTuple::new(py, items)?.unbind().into_any())
}

fn object<'py, T: IntoPyObject<'py>>(py: Python<'py>, value: T) -> PyResult<PyObject> {
    value.into_py_any(py)
}

fn outcome_object<T>(
    py: Python<'_>,
    outcome: FileOutcome<T>,
    parsed: impl FnOnce(Python<'_>, T) -> PyResult<PyObject>,
) -> PyResult<PyObject> {
    match outcome {
        FileOutcome::Parsed(value) => parsed(py, value),
        FileOutcome::Unreadable => tuple_object(py, vec![object(py, "read")?]),
        FileOutcome::Failed(failure) => tuple_object(
            py,
            vec![
                object(py, "error")?,
                object(py, failure.kind.as_str())?,
                object(py, failure.message)?,
                object(py, failure.help)?,
            ],
        ),
    }
}

fn model_object(py: Python<'_>, model: DiscoveredModelFile) -> PyResult<PyObject> {
    tuple_object(
        py,
        vec![
            object(py, "ok")?,
            object(py, model.contents)?,
            map_to_python(py, model.header_values)?,
            object(py, located(model.header_column_locations))?,
            object(py, located(model.output_column_locations))?,
            object(py, model.query_sql)?,
        ],
    )
}

fn files_object<T>(
    py: Python<'_>,
    files: Vec<DiscoveredFile<T>>,
    parsed: impl Fn(Python<'_>, T) -> PyResult<PyObject>,
) -> PyResult<Vec<(String, PyObject)>> {
    files
        .into_iter()
        .map(|file| {
            Ok((
                file.relative_path,
                outcome_object(py, file.outcome, &parsed)?,
            ))
        })
        .collect()
}

/// Discover the model files natively, or return `None` when Python must run the stage.
#[pyfunction]
fn discover_model_files(
    py: Python<'_>,
    request: ModelDiscoveryRequest,
) -> PyResult<Option<Vec<(String, PyObject)>>> {
    let root = ProjectRoot {
        directory: PathBuf::from(request.project_dir),
        display_prefix: request.display_prefix,
    };
    let options = ModelFileOptions {
        supported_keys: request.supported_keys,
        removed_keys: request.removed_keys,
        extract_implicit_alias_columns: request.extract_implicit_alias_columns,
        extract_output_column_locations: request.extract_output_column_locations,
    };
    let discovered: Result<Vec<DiscoveredFile<DiscoveredModelFile>>, StageDeferral> = py
        .compiler_detach(|| {
            let tree = ProjectTree::new(&root.directory);
            Ok(discover_models(&root, &tree, &options))
        })
        .map_err(crate::bindings::_helpers::panics::compiler_error)?;
    match discovered {
        Ok(files) => Ok(Some(files_object(py, files, model_object)?)),
        Err(_deferral) => Ok(None),
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(discover_model_files, module)?)?;
    Ok(())
}
