//! The external columns a model's query reads.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::required_columns::errors::RequiredColumnsError;
use sqlbuild_analysis::required_columns::main::resolve_required_columns::resolve_required_columns as resolve;
use sqlbuild_analysis::required_columns::models::{ColumnRead, ReferenceInput};

use crate::bindings::_helpers::boundary::panics::value_error;
use crate::bindings::types::CompilerDetach;

/// Each `(resource type, resource, column)` the query reads, given its `(kind, name)` references.
#[pyfunction]
#[pyo3(signature = (query_sql, references, dialect))]
fn resolve_required_columns(
    py: Python<'_>,
    query_sql: &str,
    references: Vec<(String, String)>,
    dialect: Option<&str>,
) -> PyResult<Vec<(String, String, String)>> {
    let references: Vec<ReferenceInput> = references
        .into_iter()
        .map(|(kind, name)| ReferenceInput { kind, name })
        .collect();
    let reads: Vec<ColumnRead> = py
        .compiler_detach(|| Ok(resolve(query_sql, &references, dialect)))
        .map_err(value_error)?
        .map_err(|error| match error {
            RequiredColumnsError::UnknownDialect(name) => {
                PyValueError::new_err(format!("Unknown dialect: {name}"))
            }
            RequiredColumnsError::Normalization(message) => value_error(message),
        })?;
    Ok(reads
        .into_iter()
        .map(|read| (read.resource_type, read.resource_name, read.column_name))
        .collect())
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(resolve_required_columns, module)?)
}
