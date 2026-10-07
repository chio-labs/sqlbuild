//! Match, tokenize and parse model headers natively.

use pyo3::prelude::{Bound, Py, PyAny, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::boundary::panics::{compiler_guard, value_error};
use crate::bindings::_helpers::sqltext::authored_values::optional_authored_value_to_python;
use crate::bindings::types::CompilerDetach;

type ParsedModelHeader = (
    Option<Py<PyAny>>,
    Option<Vec<(String, usize, usize)>>,
    Option<String>,
);

#[pyfunction]
fn parse_model_headers(py: Python<'_>, headers: Vec<String>) -> PyResult<Vec<ParsedModelHeader>> {
    let parsed = py
        .compiler_detach(|| {
            sqlbuild_sqltext::compiler::main::model_header_parsing::parse_batch(&headers)
        })
        .map_err(value_error)?;
    parsed
        .into_iter()
        .map(|(value, offsets, error)| {
            Ok((
                optional_authored_value_to_python(py, value)?,
                offsets,
                error,
            ))
        })
        .collect()
}

#[pyfunction]
fn match_model_headers(
    py: Python<'_>,
    contents: Vec<String>,
) -> PyResult<Vec<Option<(usize, usize, usize)>>> {
    py.compiler_detach(|| {
        Ok(sqlbuild_sqltext::compiler::main::model_header_matching::match_batch(&contents))
    })
    .map_err(value_error)
}

#[pyfunction]
fn tokenize_model_header(header: &str) -> PyResult<Vec<(u8, String, usize)>> {
    compiler_guard(|| {
        sqlbuild_sqltext::compiler::main::model_header_tokenizing::tokenize_one(header)
            .map_err(value_error)
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(parse_model_headers, module)?)?;
    module.add_function(wrap_pyfunction!(match_model_headers, module)?)?;
    module.add_function(wrap_pyfunction!(tokenize_model_header, module)?)?;
    Ok(())
}
