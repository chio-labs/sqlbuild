//! Query and function definition fingerprints for change detection, failing as planner input errors.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::PyString;
use pyo3::{pyfunction, wrap_pyfunction};

use sqlbuild_analysis::planner_identity::constants::{FINGERPRINT_HELP, QUERY_FINGERPRINT_FAILED};
use sqlbuild_analysis::planner_identity::models::GraphKey;
use sqlbuild_analysis::sql_tokens::main::compiler_query_fingerprint::compiler_query_fingerprint;
use sqlbuild_analysis::sql_tokens::main::definition_fingerprint::definition_fingerprint;
use sqlbuild_core::panics::main::is_compiler_panic::is_compiler_panic;

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::_helpers::compile_driver::python_calls::keywords;
use crate::bindings::_helpers::records::construct::error_class;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::ids::ErrorId;
use crate::bindings::types::CompilerDetach;

/// The query fingerprint of a model, or the planner input error naming the model.
pub(crate) fn model_query_hash(
    py: Python<'_>,
    model_name: &str,
    (query_sql, dialect): (&str, Option<&str>),
) -> PyResult<String> {
    py.compiler_detach(|| compiler_query_fingerprint(query_sql, dialect))
        .map_err(|error| fingerprint_error(py, &format!("Model '{model_name}' SQL"), error))
}

/// The definition fingerprint of a function, or the planner input error naming the function.
pub(crate) fn function_definition_hash(
    py: Python<'_>,
    function_name: &str,
    (fingerprint_sql, language, dialect): (&str, &str, Option<&str>),
) -> PyResult<String> {
    py.compiler_detach(|| definition_fingerprint(fingerprint_sql, language, dialect))
        .map_err(|error| fingerprint_error(py, &format!("Function '{function_name}'"), error))
}

fn fingerprint_error(py: Python<'_>, subject: &str, message: String) -> PyErr {
    if is_compiler_panic(&message) {
        return compiler_error(message);
    }
    let text = |value: &str| PyString::new(py, value).into_any();
    let raised: PyResult<Bound<'_, PyAny>> =
        error_class(py, ErrorId::PlannerInput).and_then(|class| {
            class.call(
                (format!(
                    "{subject} cannot be fingerprinted for change detection: {message}"
                ),),
                Some(&keywords(
                    py,
                    &[
                        ("code", text(QUERY_FINGERPRINT_FAILED)),
                        ("help", text(FINGERPRINT_HELP)),
                    ],
                )?),
            )
        });
    match raised {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}

/// The graph key of a `CompiledObjectKey`-like value: its resource type text and name.
pub(crate) fn graph_key(key: &Bound<'_, PyAny>) -> PyResult<GraphKey> {
    Ok(GraphKey {
        kind: native_field(key, "resource_type")?.str()?.extract()?,
        name: native_field(key, "name")?.extract()?,
    })
}

/// Fingerprint a model query for change detection, naming the model when it cannot.
#[pyfunction]
#[pyo3(signature = (*, model_name, query_sql, dialect))]
pub(crate) fn model_definition_hash(
    py: Python<'_>,
    model_name: &str,
    query_sql: &str,
    dialect: Option<&str>,
) -> PyResult<String> {
    model_query_hash(py, model_name, (query_sql, dialect))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(model_definition_hash, module)?)
}
