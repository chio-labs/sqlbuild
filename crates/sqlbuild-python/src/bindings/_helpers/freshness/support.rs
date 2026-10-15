//! Python objects, exceptions and datetimes the source freshness glue shares.

use pyo3::exceptions::PyException;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyDict, PyString};

use crate::bindings::_helpers::compile_driver::python_calls::imported;
use crate::bindings::_helpers::cursor::values::DATETIME_MODULE;
use crate::bindings::_helpers::state_rows::timestamps::{date_time_typed, in_utc, offset_aware};

pub(crate) const EXCEPTIONS_MODULE: &str = "sqlbuild._native";
pub(crate) const FRESHNESS_MODELS: &str = "sqlbuild._native";
pub(crate) const FRESHNESS_CONSTANTS: &str = "sqlbuild.compiler.source_freshness.constants";
pub(crate) const CONTRACT_MODELS: &str = "sqlbuild._native";
pub(crate) const CONTRACT_TYPES: &str = "sqlbuild._native";
pub(crate) const ADAPTER_MODELS: &str = "sqlbuild.adapter.contract.models";
pub(crate) const ADAPTER_TYPES: &str = "sqlbuild.adapter.contract.types";
pub(crate) const ADAPTER_EXCEPTIONS: &str = "sqlbuild.adapter.contract.exceptions";
pub(crate) const LIFECYCLE_MODULE: &str =
    "sqlbuild.runtime.observability.classes.operation_lifecycle";
pub(crate) const OBSERVABILITY_MODELS: &str = "sqlbuild.runtime.observability.models";
pub(crate) const STATE_TABLE_DDL_MODULE: &str =
    "sqlbuild.adapter.state_sql.main.render_state_table_create_sql";
pub(crate) const OBSERVATION_ERROR: &str = "SourceFreshnessObservationError";
pub(crate) const INPUT_ERROR: &str = "SourceFreshnessInputError";

/// `exceptions.<class>(message)` as a raisable error, with an optional `__cause__`.
pub(crate) fn freshness_error(
    py: Python<'_>,
    (class, message): (&str, &str),
    cause: Option<PyErr>,
) -> PyErr {
    let error: PyErr =
        match imported(py, EXCEPTIONS_MODULE, class).and_then(|class| class.call1((message,))) {
            Ok(error) => PyErr::from_value(error),
            Err(error) => return error,
        };
    if let Some(cause) = cause {
        error.set_cause(py, Some(cause));
    }
    error
}

/// `str(exc)` of an `Exception`, or the error itself for anything else.
pub(crate) fn exception_text(py: Python<'_>, error: &PyErr) -> PyResult<Option<String>> {
    if !error.is_instance_of::<PyException>(py) {
        return Ok(None);
    }
    Ok(Some(error.value(py).str()?.extract()?))
}

/// `value` when it is not a `datetime`; otherwise in UTC, a naive value read as UTC.
pub(crate) fn presumed_utc_value<'py>(value: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    if !date_time_typed(value)? {
        return Ok(value.clone());
    }
    presumed_utc_datetime(value)
}

/// A `datetime` in UTC, a naive or offset-less value read as UTC.
pub(crate) fn presumed_utc_datetime<'py>(value: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    if offset_aware(value)? {
        return in_utc(value);
    }
    let changes: Bound<'py, PyDict> = PyDict::new(value.py());
    changes.set_item("tzinfo", imported(value.py(), DATETIME_MODULE, "UTC")?)?;
    value.call_method("replace", (), Some(&changes))
}

pub(crate) fn text<'py>(py: Python<'py>, value: &str) -> Bound<'py, PyAny> {
    PyString::new(py, value).into_any()
}

/// `str(value)`, or `None` for `None`.
pub(crate) fn optional_str<'py>(value: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    if value.is_none() {
        return Ok(value.clone());
    }
    Ok(value.str()?.into_any())
}
