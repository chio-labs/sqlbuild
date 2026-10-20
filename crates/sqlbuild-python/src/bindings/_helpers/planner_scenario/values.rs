//! Existing Python model constructors and scenario diagnostics.

use crate::bindings::_helpers::boundary::python_calls::call_with;
use crate::bindings::_helpers::records::construct::error_class;
use crate::bindings::_helpers::records::ids::ErrorId;
use pyo3::prelude::{Bound, PyAny, PyErr, PyResult, Python};
use pyo3::types::PyString;

pub(super) fn string<'py>(py: Python<'py>, text: &str) -> Bound<'py, PyAny> {
    PyString::new(py, text).into_any()
}

pub(super) fn error(
    py: Python<'_>,
    message: &str,
    code: &str,
    help: Option<&str>,
) -> PyResult<PyErr> {
    let mut args = vec![("message", string(py, message)), ("code", string(py, code))];
    if let Some(help) = help {
        args.push(("help", string(py, help)));
    }
    Ok(PyErr::from_value(call_with(
        &error_class(py, ErrorId::PlannerInput)?,
        &args,
    )?))
}
