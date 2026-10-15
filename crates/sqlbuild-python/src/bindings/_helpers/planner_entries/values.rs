//! Python boundary values shared by plan entry and plan output assembly.

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, keywords};
use pyo3::IntoPyObject;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::PyString;

pub(super) const NATIVE_MODULE: &str = "sqlbuild._native";
pub(super) const PLANNER_MODELS: &str = "sqlbuild.compiler.planner.models";
pub(super) const PLANNER_TYPES: &str = "sqlbuild.compiler.planner.types";
pub(super) const PLANNER_EXCEPTIONS: &str = "sqlbuild.compiler.planner.exceptions";
pub(super) const PLANNER_CONSTANTS: &str = "sqlbuild.compiler.planner.constants";
pub(super) const COMPILE_EXCEPTIONS: &str = "sqlbuild.compiler.compile.exceptions";
pub(super) const COMPILE_TYPES: &str = "sqlbuild.compiler.compile.types";

/// `sqlbuild._native.name(**pairs)`.
pub(super) fn native<'py>(
    py: Python<'py>,
    name: &str,
    pairs: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    call_with(&imported(py, NATIVE_MODULE, name)?, pairs)
}

/// `sqlbuild.compiler.planner.models.name(**pairs)`.
pub(super) fn planner_model<'py>(
    py: Python<'py>,
    name: &str,
    pairs: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    call_with(&imported(py, PLANNER_MODELS, name)?, pairs)
}

/// One member of a planner enumeration.
pub(super) fn planner_type<'py>(
    py: Python<'py>,
    class: &str,
    member: &str,
) -> PyResult<Bound<'py, PyAny>> {
    imported(py, PLANNER_TYPES, class)?.getattr(member)
}

/// A Python string.
pub(super) fn string<'py>(py: Python<'py>, text: &str) -> Bound<'py, PyAny> {
    PyString::new(py, text).into_any()
}

/// A Python bool.
pub(super) fn boolean(py: Python<'_>, value: bool) -> PyResult<Bound<'_, PyAny>> {
    Ok(value.into_pyobject(py)?.to_owned().into_any())
}

/// `None`.
pub(super) fn none(py: Python<'_>) -> Bound<'_, PyAny> {
    py.None().into_bound(py)
}

/// `dataclasses.replace(object, **fields)`.
pub(super) fn replaced<'py>(
    object: &Bound<'py, PyAny>,
    fields: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    imported(object.py(), "dataclasses", "replace")?
        .call((object,), Some(&keywords(object.py(), fields)?))
}

/// `class(message, **fields)` from `module`, as a raised error.
pub(super) fn error_of(
    py: Python<'_>,
    (module, class): (&str, &str),
    message: &str,
    fields: &[(&str, Bound<'_, PyAny>)],
) -> PyErr {
    match imported(py, module, class)
        .and_then(|class| class.call((message,), Some(&keywords(py, fields)?)))
    {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}
