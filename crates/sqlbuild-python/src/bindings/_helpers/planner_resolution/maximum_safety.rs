//! Maximum automatic-start recovery and evidence boundary.

use crate::bindings::_helpers::compile_driver::python_calls::keywords;
use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, call_with};
use crate::bindings::_helpers::cursor::conversion::CursorSession;
use crate::bindings::_helpers::cursor::scalars::render_value;
use crate::bindings::_helpers::planner_phases::objects::object;
use crate::bindings::_helpers::planner_resolution::cursor_bounds::apply_typed_cursor_replay_policy;
use crate::bindings::_helpers::planner_resolution::cursor_bounds::{
    optional_scalar, required_scalar, scalars,
};
use crate::bindings::_helpers::planner_resolution::cursor_safety::{
    horizon, replace, safety_duration, safety_error, timestamp_bound, utc_clock,
};
use crate::bindings::_helpers::planner_resolution::values::string;
use crate::bindings::_helpers::records::ids::{ErrorId, RecordId};
use crate::bindings::_helpers::records::registry;
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::PyDict;
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_cursor::algebra::main::compare::compare;
use sqlbuild_cursor::algebra::main::render::render;
use sqlbuild_cursor::planner::main::eligible_start::eligible_start;
use std::cmp::Ordering;

#[pyfunction]
#[pyo3(signature = (**kwargs))]
pub(crate) fn maximum_allowed_start<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<String> {
    let args = KeywordArguments::read(
        py,
        "maximum_allowed_start",
        kwargs,
        (
            &[
                "discovered_value",
                "cursor_grain",
                "invocation_time",
                "max_ahead",
            ],
            &[],
        ),
    )?;
    let session = CursorSession::new(py)?;
    let discovered = required_scalar(
        &session,
        &args.value("discovered_value")?,
        &string(py, "timestamp"),
    )?;
    let duration = safety_duration(&args.value("max_ahead")?, false)?;
    session.checked(render(
        &horizon(
            &session,
            &session.python_scalar(&discovered)?,
            (
                &args.value("invocation_time")?,
                &args.value("cursor_grain")?,
            ),
            &duration,
        )?,
        &session,
    ))
}

#[pyfunction]
#[pyo3(signature = (**kwargs))]
pub(crate) fn apply_maximum_start_policy<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "apply_maximum_start_policy",
        kwargs,
        (
            &[
                "bounds",
                "snapshot",
                "cursor_type",
                "cursor_grain",
                "cursor_start",
                "lookback",
                "backfill_duration",
                "policy",
                "has_start_override",
            ],
            &[],
        ),
    )?;
    let bounds = args.value("bounds")?;
    let snapshot = args.value("snapshot")?;
    let physical = snapshot.getattr("physical_target_max")?;
    let physical = if physical.is_truthy()? {
        physical
    } else {
        snapshot.getattr("target_max")?
    };
    let policy = args.value("policy")?;
    let config = policy.getattr("config")?;
    let clock = policy.getattr("invocation_time")?;
    if config.is_none()
        || config.getattr("max_ahead")?.is_none()
        || !args.value("cursor_type")?.eq("timestamp")?
        || clock.is_none()
        || args.flag("has_start_override")?
        || physical.is_none()
    {
        return Ok(bounds);
    }
    if !timestamp_bound(&bounds.getattr("start")?)? || !timestamp_bound(&bounds.getattr("end")?)? {
        return Ok(bounds);
    }
    let duration = safety_duration(&config.getattr("max_ahead")?, false)?;
    if !timestamp_bound(&physical)? {
        return Err(safety_error(
            py,
            ErrorId::MaximumAutomaticStart,
            "automatic start requires a timestamp cursor",
        ));
    }
    let session = CursorSession::new(py)?;
    let horizon = horizon(
        &session,
        &physical,
        (&clock, &args.value("cursor_grain")?),
        &duration,
    )?;
    let physical_typed = session.scalar(&physical)?;
    if session.checked(compare(&physical_typed, &horizon, &session))? != Ordering::Greater {
        return Ok(bounds);
    }
    let target = optional_scalar(&session, &snapshot.getattr("target_eligible_max")?)?;
    let upstream = if target.is_none() {
        scalars(&session, &snapshot, "upstream_mins")?
    } else {
        Vec::new()
    };
    let mut eligible = session.checked(eligible_start(
        target.as_ref(),
        &upstream,
        &horizon,
        &session,
    ))?;
    if eligible.is_none() {
        let floor = args.value("cursor_start")?;
        if !floor.is_none() {
            let floor = if timestamp_bound(&floor)? {
                session.scalar(&floor)?
            } else {
                required_scalar(&session, &floor, &string(py, "timestamp"))?
            };
            if session.checked(compare(&floor, &horizon, &session))? != Ordering::Greater {
                eligible = Some(floor);
            }
        }
    }
    let effective = if let Some(eligible) = &eligible {
        let mut replay = vec![
            ("start", session.python_scalar(eligible)?),
            ("end", bounds.getattr("end")?),
            (
                "has_start_override",
                false.into_pyobject(py)?.to_owned().into_any(),
            ),
        ];
        for key in [
            "cursor_start",
            "cursor_type",
            "lookback",
            "backfill_duration",
        ] {
            replay.push((key, args.value(key)?));
        }
        apply_typed_cursor_replay_policy(py, Some(keywords(py, &replay)?))?
    } else {
        bounds.getattr("start")?
    };
    let relation = snapshot.getattr("target_relation")?;
    let column = snapshot.getattr("destination_cursor_column")?;
    let evidence = call_with(
        &registry::class(py, RecordId::MaximumStartSafetyEvidence)?,
        &[
            ("action", config.getattr("action")?),
            ("max_ahead", config.getattr("max_ahead")?),
            (
                "invocation_time",
                call_with(
                    &registry::class(py, RecordId::TimestampValue)?,
                    &[("value", utc_clock(&clock)?)],
                )?,
            ),
            ("physical_target_max", physical),
            (
                "highest_eligible_target_max",
                snapshot.getattr("target_eligible_max")?,
            ),
            ("effective_start", effective.clone()),
            ("maximum_allowed_start", session.python_scalar(&horizon)?),
            (
                "target_relation",
                if relation.is_truthy()? {
                    relation
                } else {
                    string(py, "")
                },
            ),
            (
                "cursor_column",
                if column.is_truthy()? {
                    column
                } else {
                    string(py, "")
                },
            ),
        ],
    )?;
    let error = |non_idempotent: bool| -> PyResult<Bound<'py, PyAny>> {
        Err(PyErr::from_value(call_with(
            &registry::error(py, ErrorId::MaximumAutomaticStart)?,
            &[
                (
                    "message",
                    string(py, &exceeded_message(&evidence, non_idempotent)?),
                ),
                ("evidence", evidence.clone()),
            ],
        )?))
    };
    if config.getattr("action")?.eq("error")?
        || eligible.is_none()
        || session.checked(compare(&session.scalar(&effective)?, &horizon, &session))?
            == Ordering::Greater
    {
        return error(false);
    }
    let strategy = policy.getattr("incremental_strategy")?;
    if !strategy.eq("delete_insert")? && !strategy.eq("merge")? {
        return error(true);
    }
    replace(
        &bounds,
        &[("start", effective), ("maximum_start_safety", evidence)],
    )
}

fn rendered(value: &Bound<'_, PyAny>) -> PyResult<String> {
    object(value.py(), render_value(value)?)?.extract()
}

/// The message of an automatic start that exceeds its horizon.
fn exceeded_message(evidence: &Bound<'_, PyAny>, non_idempotent: bool) -> PyResult<String> {
    let detail: &str = if non_idempotent {
        " on a non-idempotent materialization"
    } else {
        ""
    };
    let highest = evidence.getattr("highest_eligible_target_max")?;
    let highest: String = if highest.is_none() {
        "None".to_owned()
    } else {
        string(evidence.py(), &rendered(&highest)?)
            .repr()?
            .to_string()
    };
    Ok(format!(
        "maximum automatic start policy exceeded{detail}: physical target MAX='{}', highest eligible MAX={highest}, effective post-lookback start='{}', horizon='{}', action={}, input={}.{}",
        rendered(&evidence.getattr("physical_target_max")?)?,
        rendered(&evidence.getattr("effective_start")?)?,
        rendered(&evidence.getattr("maximum_allowed_start")?)?,
        evidence.getattr("action")?.getattr("value")?.str()?,
        evidence.getattr("target_relation")?.str()?,
        evidence.getattr("cursor_column")?.str()?,
    ))
}

pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(maximum_allowed_start, module)?)?;
    module.add_function(wrap_pyfunction!(apply_maximum_start_policy, module)?)
}
