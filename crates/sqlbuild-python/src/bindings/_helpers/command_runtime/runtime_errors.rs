//! The Python exceptions command connection failures are raised as.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods};
use sqlbuild_config::command_connection::errors::CommandConnectionError;

use crate::bindings::_helpers::compile_driver::python_calls::imported;

const CLI_ERRORS_MODULE: &str = "sqlbuild._native";
const DISCOVERY_ERRORS_MODULE: &str = "sqlbuild._native";
const COMPILE_ERRORS_MODULE: &str = "sqlbuild._native";

/// The `CliUserError` or `ProjectConfigError` for `error`.
pub(crate) fn raised(py: Python<'_>, error: CommandConnectionError) -> PyErr {
    let created = || -> PyResult<PyErr> {
        let instance: Bound<'_, PyAny> = match error {
            CommandConnectionError::User {
                code,
                message,
                help,
            } => {
                let keywords: Bound<'_, PyDict> = PyDict::new(py);
                keywords.set_item("code", code)?;
                keywords.set_item("help", help)?;
                imported(py, CLI_ERRORS_MODULE, "CliUserError")?
                    .call((message,), Some(&keywords))?
            }
            CommandConnectionError::ProjectConfig(message) => {
                imported(py, DISCOVERY_ERRORS_MODULE, "ProjectConfigError")?.call1((message,))?
            }
        };
        Ok(PyErr::from_value(instance))
    };
    created().unwrap_or_else(|failure| failure)
}

/// Whether `error` is a `CompileInputError` or a `CliUserError`, the failures resolution reports.
pub(crate) fn expected_resolution_error(py: Python<'_>, error: &PyErr) -> PyResult<bool> {
    Ok(
        error.is_instance(py, &imported(py, CLI_ERRORS_MODULE, "CliUserError")?)
            || error.is_instance(
                py,
                &imported(py, COMPILE_ERRORS_MODULE, "CompileInputError")?,
            ),
    )
}

/// The message a resolution error shows: `CliUserError.message`, else `str(error)`.
pub(crate) fn resolution_message(py: Python<'_>, error: &PyErr) -> PyResult<String> {
    let value: Bound<'_, PyAny> = error.value(py).clone().into_any();
    if error.is_instance(py, &imported(py, CLI_ERRORS_MODULE, "CliUserError")?) {
        return value.getattr("message")?.str()?.extract();
    }
    value.str()?.extract()
}
