//! Hooks applied while building native records.

use pyo3::prelude::{Bound, Py, PyAny, PyResult, Python};
use pyo3::types::{PyDict, PyTuple};

/// Normalizes the bound field values of one record before it is created.
pub(crate) type RecordFinish = fn(Python<'_>, Vec<Py<PyAny>>) -> PyResult<Vec<Py<PyAny>>>;

/// Computes one read-only attribute of a native class instance.
pub(crate) type ClassProperty = fn(&Bound<'_, PyAny>) -> PyResult<Py<PyAny>>;

/// Runs one method of a native class with its receiver (the instance, or the class when unbound).
pub(crate) type ClassMethod =
    fn(&Bound<'_, PyAny>, &Bound<'_, PyTuple>, Option<&Bound<'_, PyDict>>) -> PyResult<Py<PyAny>>;

/// Builds the default value of one record field.
pub(crate) type RecordFactory = fn(Python<'_>) -> PyResult<Bound<'_, PyAny>>;
