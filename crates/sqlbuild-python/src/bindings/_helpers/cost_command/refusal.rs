//! Cost command errors raised as `CliUserError`.

use pyo3::prelude::{Bound, PyAnyMethods, PyErr, Python};
use pyo3::types::{PyDict, PyDictMethods};
use sqlbuild_core::cost_command::errors::CostCommandError;

use crate::bindings::_helpers::compile_driver::python_calls::imported;

const ERRORS_MODULE: &str = "sqlbuild._native";

/// The `CliUserError` for a refused cost request.
pub(crate) fn cost_error(py: Python<'_>, error: &CostCommandError) -> PyErr {
    let raised = (|| {
        let options: Bound<'_, PyDict> = PyDict::new(py);
        options.set_item("code", error.code)?;
        imported(py, ERRORS_MODULE, "CliUserError")?.call((error.message.as_str(),), Some(&options))
    })();
    match raised {
        Ok(error) => PyErr::from_value(error),
        Err(failure) => failure,
    }
}
