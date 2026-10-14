//! Future cursor safety evidence and exception boundary.

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::cursor::conversion::CursorSession;
use crate::bindings::_helpers::planner_resolution::cursor_safety::{
    MODELS, horizon, replace, safety_duration, safety_error, timestamp_bound, utc_clock,
};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyTuple};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_cursor::algebra::main::compare::compare;
use sqlbuild_cursor::algebra::main::next_boundary::next_boundary;
use sqlbuild_cursor::algebra::main::render::render;
use sqlbuild_cursor::algebra::models::{Grain, Scalar};
use std::cmp::Ordering;

#[pyfunction]
#[pyo3(signature = (**kwargs))]
fn resolve_future_cursor_safety<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "resolve_future_cursor_safety",
        kwargs,
        (
            &[
                "bounds",
                "cursor_type",
                "cursor_grain",
                "config",
                "invocation_time",
                "has_complete_override",
            ],
            &["input_evidence"],
        ),
    )?;
    let bounds = args.value("bounds")?;
    let config = args.value("config")?;
    let clock = args.value("invocation_time")?;
    if config.is_none()
        || config.getattr("max_distance")?.is_none()
        || !args.value("cursor_type")?.eq("timestamp")?
        || clock.is_none()
        || args.flag("has_complete_override")?
    {
        return Ok(bounds);
    }
    let distance = config.getattr("max_distance")?;
    let duration = safety_duration(&distance, true)?;
    let start = bounds.getattr("start")?;
    let end = bounds.getattr("end")?;
    if !timestamp_bound(&start)? || !timestamp_bound(&end)? {
        return Ok(bounds);
    }
    let session = CursorSession::new(py)?;
    let grain = args.value("cursor_grain")?;
    let allowed_start = horizon(&session, &end, (&clock, &grain), &duration)?;
    let grain = if grain.is_truthy()? {
        session.grain(&grain)?.unwrap_or(Grain::Second)
    } else {
        Grain::Second
    };
    let allowed_end = session.checked(next_boundary(&allowed_start, Some(grain)))?;
    let typed_start = session.scalar(&start)?;
    let typed_end = session.scalar(&end)?;
    let future_start =
        session.checked(compare(&typed_start, &allowed_start, &session))? == Ordering::Greater;
    let future_end =
        session.checked(compare(&typed_end, &allowed_end, &session))? == Ordering::Greater;
    if !future_start && !future_end {
        return Ok(bounds);
    }
    let evidence = args.value("input_evidence")?;
    let evidence = if evidence.is_none() {
        PyTuple::empty(py).into_any()
    } else {
        evidence
    };
    let mut determining: Option<(Bound<'py, PyAny>, Scalar)> = None;
    for item in evidence.try_iter()? {
        let item = item?;
        let maximum = session.scalar(&item.getattr("maximum")?)?;
        let smaller = if let Some((_, previous)) = &determining {
            session.checked(compare(&maximum, previous, &session))? == Ordering::Less
        } else {
            true
        };
        if smaller {
            determining = Some((item, maximum));
        }
    }
    if config.getattr("action")?.eq("error")? {
        return Err(safety_error(
            py,
            "FutureCursorSafetyError",
            &format!(
                "future cursor safety limit exceeded: effective bounds ['{}', '{}') exceed maximum allowed bounds ['{}', '{}') (cursors.future.max_distance={})",
                session.checked(render(&typed_start, &session))?,
                session.checked(render(&typed_end, &session))?,
                session.checked(render(&allowed_start, &session))?,
                session.checked(render(&allowed_end, &session))?,
                distance.str()?
            ),
        ));
    }
    let applied_end = if future_end {
        session.python_scalar(&allowed_end)?
    } else {
        end.clone()
    };
    let determining_field = |field: &str| -> PyResult<Bound<'py, PyAny>> {
        if let Some((item, _)) = &determining {
            item.getattr(field)
        } else {
            Ok(py.None().into_bound(py))
        }
    };
    let safety = call_with(
        &imported(py, MODELS, "FutureCursorSafetyEvidence")?,
        &[
            ("action", config.getattr("action")?),
            ("max_distance", distance),
            (
                "invocation_time",
                call_with(
                    &imported(py, "sqlbuild.cursor_algebra.models", "TimestampValue")?,
                    &[("value", utc_clock(&clock)?)],
                )?,
            ),
            ("discovered_start", start.clone()),
            ("discovered_end", end),
            ("applied_start", start),
            ("applied_end", applied_end.clone()),
            (
                "maximum_allowed_start",
                session.python_scalar(&allowed_start)?,
            ),
            ("maximum_allowed_end", session.python_scalar(&allowed_end)?),
            (
                "future_start_detected",
                future_start.into_pyobject(py)?.to_owned().into_any(),
            ),
            (
                "future_end_detected",
                future_end.into_pyobject(py)?.to_owned().into_any(),
            ),
            ("determining_relation", determining_field("relation")?),
            (
                "determining_cursor_column",
                determining_field("cursor_column")?,
            ),
            ("inputs", evidence),
        ],
    )?;
    replace(&bounds, &[("end", applied_end), ("future_safety", safety)])
}

pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(resolve_future_cursor_safety, module)?)
}
