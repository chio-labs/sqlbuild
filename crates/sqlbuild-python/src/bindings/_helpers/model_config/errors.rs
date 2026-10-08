//! The exact config error handed to Python.

use pyo3::pyclass;

/// One exact error: the Python class to raise, its message, code, help and named config key.
#[pyclass(module = "sqlbuild._native", frozen, get_all)]
pub(crate) struct NativeConfigError {
    pub(crate) class_name: &'static str,
    pub(crate) message: String,
    pub(crate) code: Option<&'static str>,
    pub(crate) help: Option<String>,
    pub(crate) key: Option<String>,
}
