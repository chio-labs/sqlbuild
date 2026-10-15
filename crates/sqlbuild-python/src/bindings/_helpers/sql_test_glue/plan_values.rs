//! Python value boundaries shared by SQL-test plan assembly.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::PyString;

use crate::bindings::_helpers::compile_driver::python_calls::imported;

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";

pub(super) fn string<'py>(py: Python<'py>, value: &str) -> Bound<'py, PyAny> {
    PyString::new(py, value).into_any()
}

pub(super) fn model_payload(test: &Bound<'_, PyAny>) -> PyResult<bool> {
    test.getattr("payload")?.is_instance(&imported(
        test.py(),
        NATIVE_RECORDS_MODULE,
        "CompiledModelSqlTestPayload",
    )?)
}

pub(super) fn tuple<'py>(value: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    imported(value.py(), "builtins", "tuple")?.call1((value,))
}
