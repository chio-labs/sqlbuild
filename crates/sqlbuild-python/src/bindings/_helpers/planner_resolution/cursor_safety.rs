//! Shared safety horizon conversion and Python evidence construction.

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, keywords};
use crate::bindings::_helpers::cursor::conversion::CursorSession;
use crate::bindings::_helpers::planner_resolution::cursor_bounds::duration;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use sqlbuild_cursor::algebra::models::{DurationSpan, Grain, Scalar};
use sqlbuild_cursor::planner::main::safety_horizon::safety_horizon;

pub(super) const MODELS: &str = "sqlbuild.compiler.planner.models";
pub(super) const EXCEPTIONS: &str = "sqlbuild.compiler.planner.exceptions";

pub(super) fn safety_error(py: Python<'_>, class: &str, message: &str) -> PyErr {
    match imported(py, EXCEPTIONS, class).and_then(|class| class.call1((message,))) {
        Ok(value) => PyErr::from_value(value),
        Err(error) => error,
    }
}

pub(super) fn safety_duration(value: &Bound<'_, PyAny>, future: bool) -> PyResult<DurationSpan> {
    if let Some(parsed) = duration(value)? {
        return Ok(parsed);
    }
    if value.eq("0d")? {
        return Ok(DurationSpan {
            months: 0,
            days: 0,
            hours: 0,
            minutes: 0,
            seconds: 0,
        });
    }
    let (class, field) = if future {
        ("FutureCursorSafetyError", "future.max_distance")
    } else {
        ("MaximumAutomaticStartError", "start.max_ahead")
    };
    Err(safety_error(
        value.py(),
        class,
        &format!("invalid cursors.{field} '{}'", value.str()?),
    ))
}

pub(super) fn timestamp_bound(value: &Bound<'_, PyAny>) -> PyResult<bool> {
    let py = value.py();
    Ok(
        value.is_instance(&imported(py, "sqlbuild._native", "DateValue")?)?
            || value.is_instance(&imported(py, "sqlbuild._native", "TimestampValue")?)?,
    )
}

pub(super) fn utc_clock<'py>(clock: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    clock.call_method1("astimezone", (imported(clock.py(), "datetime", "UTC")?,))
}

pub(super) fn horizon<'py>(
    session: &CursorSession<'py>,
    discovered: &Bound<'py, PyAny>,
    clock_and_grain: (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    span: &DurationSpan,
) -> PyResult<Scalar> {
    let py = session.py();
    let (clock, grain) = clock_and_grain;
    let mut clock = utc_clock(clock)?;
    let date_only = discovered.is_instance(&imported(py, "sqlbuild._native", "DateValue")?)?;
    if date_only || discovered.getattr("value")?.getattr("tzinfo")?.is_none() {
        clock = call_with(
            &clock.getattr("replace")?,
            &[("tzinfo", py.None().into_bound(py))],
        )?;
    }
    let clock = call_with(
        &imported(py, "sqlbuild._native", "TimestampValue")?,
        &[("value", clock)],
    )?;
    let grain = if grain.is_truthy()? {
        session.grain(grain)?.unwrap_or(Grain::Second)
    } else {
        Grain::Second
    };
    session.checked(safety_horizon(
        &session.scalar(&clock)?,
        span,
        grain,
        date_only,
    ))
}

pub(super) fn replace<'py>(
    object: &Bound<'py, PyAny>,
    fields: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    imported(object.py(), "dataclasses", "replace")?
        .call((object,), Some(&keywords(object.py(), fields)?))
}
