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

type ColumnLocation = (String, usize, usize, usize, usize);

fn location_rows(
    locations: Vec<(String, sqlbuild_sqltext::compiler::models::TextLocation)>,
) -> Vec<ColumnLocation> {
    locations
        .into_iter()
        .map(|(name, location)| {
            (
                name,
                location.line,
                location.column,
                location.end_line,
                location.end_column,
            )
        })
        .collect()
}

/// Simple top-level SELECT output names and their authored locations.
#[pyfunction]
fn model_output_columns(contents: &str, implicit_aliases: bool) -> PyResult<Vec<ColumnLocation>> {
    compiler_guard(|| {
        Ok(location_rows(
            sqlbuild_sqltext::compiler::main::model_output_columns::model_output_columns(
                contents,
                implicit_aliases,
            ),
        ))
    })
}

/// The authored locations of a header's column names, or the header's syntax error.
#[pyfunction]
fn model_header_column_locations(
    contents: &str,
    header: &str,
    header_start: usize,
) -> PyResult<(Option<Vec<ColumnLocation>>, Option<String>)> {
    compiler_guard(|| {
        Ok(
            match sqlbuild_sqltext::compiler::main::model_header_column_locations::model_header_column_locations(
                contents,
                header,
                header_start,
            ) {
                Ok(locations) => (Some(location_rows(locations)), None),
                Err(error) => (None, Some(error)),
            },
        )
    })
}

/// A header syntax error's detail, help and file line (when `header_line` is known).
#[pyfunction]
#[pyo3(signature = (error, header, header_line))]
fn model_header_failure(
    error: &str,
    header: &str,
    header_line: Option<usize>,
) -> (String, Option<String>, Option<usize>) {
    let nesting = sqlbuild_sqltext::compiler::main::model_header_errors::header_nesting_failure(
        error,
        header,
        header_line.unwrap_or(1),
    );
    match (nesting, header_line) {
        (Some(nesting), Some(_)) => (nesting.message, Some(nesting.help), Some(nesting.line)),
        (Some(nesting), None) => (error.to_owned(), Some(nesting.help), None),
        (None, _) => (error.to_owned(), None, None),
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(parse_model_headers, module)?)?;
    module.add_function(wrap_pyfunction!(match_model_headers, module)?)?;
    module.add_function(wrap_pyfunction!(tokenize_model_header, module)?)?;
    module.add_function(wrap_pyfunction!(model_output_columns, module)?)?;
    module.add_function(wrap_pyfunction!(model_header_column_locations, module)?)?;
    module.add_function(wrap_pyfunction!(model_header_failure, module)?)?;
    Ok(())
}
