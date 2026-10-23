//! Register `sqb review` and the review schema name parser the janitor uses.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::review_command::main::parse_review_schema_name::parse_review_schema_name as parse_name;

use crate::bindings::_helpers::boundary::python_calls::imported;
use crate::bindings::_helpers::review_command::command;

/// The aware UTC creation time a strict review schema name encodes, or `None`.
#[pyfunction]
#[pyo3(signature = (name, /))]
pub(crate) fn parse_review_schema_name<'py>(
    py: Python<'py>,
    name: &str,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let Some((year, month, day, hour, minute, second)) = parse_name(name) else {
        return Ok(None);
    };
    let utc: Bound<'py, PyAny> = imported(py, "datetime", "timezone")?.getattr("utc")?;
    let created = imported(py, "datetime", "datetime")?
        .call1((year, month, day, hour, minute, second, 0, utc));
    Ok(created.ok())
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(parse_review_schema_name, module)?)?;
    command::register(module)
}
