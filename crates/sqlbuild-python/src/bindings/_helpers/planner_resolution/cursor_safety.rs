//! Shared safety horizon conversion and Python evidence construction.

use crate::bindings::_helpers::boundary::python_calls::{call_with, imported, keywords};
use crate::bindings::_helpers::cursor::conversion::CursorSession;
use crate::bindings::_helpers::planner_resolution::cursor_bounds::duration;
use crate::bindings::_helpers::records::construct::error_class;
use crate::bindings::_helpers::records::construct::{new_record_with, record_class};
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::fields::replaced_keywords;
use crate::bindings::_helpers::records::ids::{ErrorId, RecordId};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use sqlbuild_cursor::algebra::models::{DurationSpan, Grain, Scalar};
use sqlbuild_cursor::planner::main::safety_horizon::safety_horizon;

pub(super) fn safety_error(py: Python<'_>, class: ErrorId, message: &str) -> PyErr {
    match error_class(py, class).and_then(|class| class.call1((message,))) {
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
        (ErrorId::FutureCursorSafety, "future.max_distance")
    } else {
        (ErrorId::MaximumAutomaticStart, "start.max_ahead")
    };
    Err(safety_error(
        value.py(),
        class,
        &format!("invalid cursors.{field} '{}'", value.str()?),
    ))
}

pub(super) fn timestamp_bound(value: &Bound<'_, PyAny>) -> PyResult<bool> {
    let py = value.py();
    Ok(value.is_instance(&record_class(py, RecordId::DateValue)?)?
        || value.is_instance(&record_class(py, RecordId::TimestampValue)?)?)
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
    let date_only = discovered.is_instance(&record_class(py, RecordId::DateValue)?)?;
    if date_only || native_field(&native_field(discovered, "value")?, "tzinfo")?.is_none() {
        clock = call_with(
            &native_field(&clock, "replace")?,
            &[("tzinfo", py.None().into_bound(py))],
        )?;
    }
    let clock = new_record_with(py, RecordId::TimestampValue, &[("value", clock)])?;
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
    replaced_keywords(object, &keywords(object.py(), fields)?)
}
