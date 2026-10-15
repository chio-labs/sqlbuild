//! Hooks applied while building native records.

use pyo3::prelude::{Py, PyAny, PyResult, Python};

/// Normalizes the bound field values of one record before it is created.
pub(crate) type RecordFinish = fn(Python<'_>, Vec<Py<PyAny>>) -> PyResult<Vec<Py<PyAny>>>;
