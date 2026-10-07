//! Validate, fingerprint and analyze SQL queries for the Python compiler.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::boundary::panics::value_error;
use crate::bindings::types::CompilerDetach;

#[pyfunction]
fn query_fingerprint(py: Python<'_>, sql: &str, dialect: &str) -> PyResult<String> {
    py.compiler_detach(|| {
        sqlbuild_analysis::sql_tokens::main::query_fingerprint::query_fingerprint(sql, dialect)
    })
    .map_err(value_error)
}

#[pyfunction(name = "validate_sql_with_schema_json")]
fn schema_validation_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.compiler_detach(|| {
        sqlbuild_analysis::semantic_validation::main::validation_json(request_json)
    })
    .map_err(value_error)
}

#[pyfunction(name = "validate_sql_with_schemas_json")]
fn schema_validations_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.compiler_detach(|| {
        sqlbuild_analysis::semantic_validation::main::validations_json(request_json)
    })
    .map_err(value_error)
}

#[pyfunction]
fn analyze_sql_uses_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.compiler_detach(|| sqlbuild_analysis::semantic_usage::main::analyze_json(request_json))
        .map_err(value_error)
}

#[pyfunction]
fn analyze_column_references_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.compiler_detach(|| {
        sqlbuild_analysis::column_references::main::analyze::analyze_json(request_json)
    })
    .map_err(value_error)
}

#[pyfunction]
fn analyze_queries_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.compiler_detach(|| {
        sqlbuild_analysis::query_analysis::main::analyze::analyze_json(request_json)
    })
    .map_err(value_error)
}

#[pyfunction]
fn analyze_project_queries_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.compiler_detach(|| {
        sqlbuild_analysis::query_analysis::main::analyze_project::analyze_project_json(request_json)
    })
    .map_err(value_error)
}

#[pyfunction]
fn analyze_project_queries_compact_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.compiler_detach(|| {
        sqlbuild_analysis::query_analysis::main::analyze_project_compact::analyze_project_compact_json(
            request_json,
        )
    })
    .map_err(value_error)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(query_fingerprint, module)?)?;
    module.add_function(wrap_pyfunction!(schema_validation_json, module)?)?;
    module.add_function(wrap_pyfunction!(schema_validations_json, module)?)?;
    module.add_function(wrap_pyfunction!(analyze_sql_uses_json, module)?)?;
    module.add_function(wrap_pyfunction!(analyze_column_references_json, module)?)?;
    module.add_function(wrap_pyfunction!(analyze_queries_json, module)?)?;
    module.add_function(wrap_pyfunction!(analyze_project_queries_json, module)?)?;
    module.add_function(wrap_pyfunction!(
        analyze_project_queries_compact_json,
        module
    )?)?;
    Ok(())
}
