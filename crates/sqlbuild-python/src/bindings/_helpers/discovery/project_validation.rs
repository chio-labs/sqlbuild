//! Cross-file validation of one discovery's inputs.

use pyo3::prelude::{Bound, PyAny, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_discovery::project_validation::main::validate_project_inputs::validate_project_inputs;
use sqlbuild_discovery::project_validation::models::{ProjectFacts, ValidationFailure};

use crate::bindings::_helpers::discovery::project_facts::{NodeRow, project_facts};
use crate::bindings::_helpers::discovery::project_files::{
    PyObject, failure_object, object, read_object, tuple_object,
};

const CSV_ERROR_TAG: &str = "csv";
const CSV_DIALECT_TAG: &str = "csv_dialect";
const UNREADABLE_TAG: &str = "unreadable";

/// `None` when the inputs are consistent, else the payload of the first error Python raises.
#[pyfunction]
fn discovered_inputs_failure(
    py: Python<'_>,
    inputs: Bound<'_, PyAny>,
    nodes: Vec<NodeRow>,
) -> PyResult<Option<PyObject>> {
    let facts: ProjectFacts = project_facts(py, &inputs, nodes)?;
    let failure: ValidationFailure = match validate_project_inputs(&facts) {
        Ok(()) => return Ok(None),
        Err(failure) => failure,
    };
    let payload: PyObject = match failure {
        ValidationFailure::Discovery(failure) => failure_object(py, failure)?,
        ValidationFailure::Unreadable {
            absolute_path,
            failure,
        } => tuple_object(
            py,
            vec![
                object(py, UNREADABLE_TAG)?,
                object(py, absolute_path)?,
                read_object(py, failure)?,
            ],
        )?,
        ValidationFailure::Csv(message) => {
            tuple_object(py, vec![object(py, CSV_ERROR_TAG)?, object(py, message)?])?
        }
        ValidationFailure::CsvDialect(error) => tuple_object(
            py,
            vec![
                object(py, CSV_DIALECT_TAG)?,
                object(py, error.class)?,
                object(py, error.message)?,
            ],
        )?,
    };
    Ok(Some(payload))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(discovered_inputs_failure, module)?)
}
