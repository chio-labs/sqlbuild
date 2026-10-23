//! Python values, errors and progress lines shared by the `sqb review` phases.

use std::time::Instant;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyString, PyTuple, PyTypeMethods};
use sqlbuild_analysis::review_command::models::{ReviewError, ReviewPlanError};

use crate::bindings::_helpers::boundary::python_calls::imported;
use crate::bindings::_helpers::records::construct::error_class;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::ids::ErrorId;

/// The code of an unexpected failure inside a review.
const UNEXPECTED_CODE: &str = "C760";

pub(crate) fn text<'py>(py: Python<'py>, value: &str) -> Bound<'py, PyAny> {
    PyString::new(py, value).into_any()
}

pub(crate) fn boolean(py: Python<'_>, value: bool) -> Bound<'_, PyAny> {
    PyBool::new(py, value).to_owned().into_any()
}

pub(crate) fn none(py: Python<'_>) -> Bound<'_, PyAny> {
    py.None().into_bound(py)
}

pub(crate) fn texts<'py>(py: Python<'py>, values: &[String]) -> PyResult<Bound<'py, PyAny>> {
    Ok(PyTuple::new(py, values)?.into_any())
}

pub(crate) fn strings(value: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    if value.is_none() {
        return Ok(Vec::new());
    }
    value
        .try_iter()?
        .map(|item| item?.str()?.extract())
        .collect()
}

pub(crate) fn optional_text(value: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if value.is_none() {
        return Ok(None);
    }
    Ok(Some(value.str()?.extract()?))
}

/// `CliUserError(message, code=code, help=help)`.
pub(crate) fn review_error(py: Python<'_>, code: &str, message: &str, help: Option<&str>) -> PyErr {
    let raised = (|| -> PyResult<Bound<'_, PyAny>> {
        let keywords: Bound<'_, PyDict> = PyDict::new(py);
        keywords.set_item("code", code)?;
        keywords.set_item("help", help)?;
        error_class(py, ErrorId::CliUser)?.call((message,), Some(&keywords))
    })();
    match raised {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}

pub(crate) fn plan_error(py: Python<'_>, error: &ReviewPlanError) -> PyErr {
    review_error(py, &error.code, &error.message, error.help.as_deref())
}

/// The code, message and help of `error`, as the report records it.
pub(crate) fn error_parts(py: Python<'_>, error: &PyErr) -> ReviewError {
    let value: Bound<'_, PyAny> = error.value(py).clone().into_any();
    let attribute = |name: &str| -> Option<String> {
        value
            .getattr_opt(name)
            .ok()
            .flatten()
            .filter(|item| !item.is_none())
            .and_then(|item| item.str().ok())
            .map(|item| item.to_string())
    };
    let message: String = attribute("message").unwrap_or_else(|| {
        value
            .str()
            .map_or_else(|_| "review failed".to_owned(), |item| item.to_string())
    });
    let message: String = if message.is_empty() {
        value
            .get_type()
            .name()
            .map_or_else(|_| "review failed".to_owned(), |name| name.to_string())
    } else {
        message
    };
    ReviewError {
        code: attribute("code").unwrap_or_else(|| UNEXPECTED_CODE.to_owned()),
        message,
        help: attribute("help"),
    }
}

/// `ReviewFailedError` carrying the reported error, chained to `cause`.
pub(crate) fn failed_error(py: Python<'_>, error: &ReviewError, cause: Option<PyErr>) -> PyErr {
    let raised = (|| -> PyResult<Bound<'_, PyAny>> {
        let keywords: Bound<'_, PyDict> = PyDict::new(py);
        keywords.set_item("code", error.code.as_str())?;
        keywords.set_item("help", error.help.as_deref())?;
        error_class(py, ErrorId::ReviewFailed)?.call((error.message.as_str(),), Some(&keywords))
    })();
    let replacement: PyErr = match raised {
        Ok(instance) => PyErr::from_value(instance),
        Err(failure) => failure,
    };
    replacement.set_cause(py, cause);
    replacement
}

/// Write `line` and a newline to `stream`, then flush.
pub(crate) fn emit(stream: &Bound<'_, PyAny>, line: &str) -> PyResult<()> {
    stream.call_method1("write", (format!("{line}\n"),))?;
    stream.call_method0("flush")?;
    Ok(())
}

/// One lifecycle phase: a start line, then a completion or failure line with its duration.
pub(crate) fn phase<T>(
    stream: &Bound<'_, PyAny>,
    (start, done, failed): (&str, &str, &str),
    body: impl FnOnce() -> PyResult<T>,
) -> PyResult<T> {
    emit(stream, &format!("{start}..."))?;
    let started: Instant = Instant::now();
    let outcome: PyResult<T> = body();
    let elapsed: f64 = started.elapsed().as_secs_f64();
    match &outcome {
        Ok(_) => emit(stream, &format!("{done} ({elapsed:.2}s)"))?,
        Err(_) => emit(stream, &format!("{failed} ({elapsed:.2}s)"))?,
    }
    outcome
}

/// Run `body` with `sys.stdout` sent to `sys.stderr` when stdout must stay machine-readable.
pub(crate) fn quietly<T>(
    py: Python<'_>,
    machine: bool,
    body: impl FnOnce() -> PyResult<T>,
) -> PyResult<T> {
    if !machine {
        return body();
    }
    let stderr: Bound<'_, PyAny> = imported(py, "sys", "stderr")?;
    let manager: Bound<'_, PyAny> =
        imported(py, "contextlib", "redirect_stdout")?.call1((stderr,))?;
    crate::bindings::_helpers::boundary::python_calls::within(&manager, |_| body())
}

/// `datetime.now(timezone.utc)`.
pub(crate) fn utc_now(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    let utc: Bound<'_, PyAny> = imported(py, "datetime", "timezone")?.getattr("utc")?;
    imported(py, "datetime", "datetime")?.call_method1("now", (utc,))
}

/// `YYYYMMDDTHHMMSSZ` of an aware UTC datetime.
pub(crate) fn compact_timestamp(moment: &Bound<'_, PyAny>) -> PyResult<String> {
    moment
        .call_method1("strftime", ("%Y%m%dT%H%M%SZ",))?
        .extract()
}

/// The current invocation id, when an invocation identity is active.
pub(crate) fn invocation_id(py: Python<'_>) -> PyResult<Option<String>> {
    let identity: Bound<'_, PyAny> = crate::bindings::_helpers::native_host::host::entry(
        py,
        sqlbuild_host::entries::models::ExecutorHost::CurrentExecutionIdentity,
    )?
    .call0()?;
    if identity.is_none() {
        return Ok(None);
    }
    optional_text(&native_field(&identity, "invocation_id")?)
}
