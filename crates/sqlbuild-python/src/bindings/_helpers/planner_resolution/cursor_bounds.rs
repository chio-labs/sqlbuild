//! Snapshot conversion and cursor window policy boundary.

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::cursor::conversion::{CursorSession, algebra_error};
use crate::bindings::_helpers::cursor::scalars::try_parse;
use crate::bindings::_helpers::planner_resolution::values::string;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::PyDict;
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_cursor::algebra::main::inclusive_to_exclusive::inclusive_to_exclusive;
use sqlbuild_cursor::algebra::models::{DurationSpan, Grain, Scalar};
use sqlbuild_cursor::planner::main::raw_bounds::raw_bounds;
use sqlbuild_cursor::planner::main::replay_start::replay_start;
use sqlbuild_cursor::planner::models::{CursorKind, CursorSnapshot, ReplayPolicy};

const MODELS: &str = "sqlbuild.compiler.planner.models";
const MAXIMUM_START: &str = "sqlbuild.compiler.planner._helpers.resolve.maximum_start";

fn optional_scalar<'py>(
    session: &CursorSession<'py>,
    value: &Bound<'py, PyAny>,
) -> PyResult<Option<Scalar>> {
    if value.is_none() {
        Ok(None)
    } else {
        session.scalar(value).map(Some)
    }
}

fn scalars<'py>(
    session: &CursorSession<'py>,
    object: &Bound<'py, PyAny>,
    field: &str,
) -> PyResult<Vec<Scalar>> {
    object
        .getattr(field)?
        .try_iter()?
        .map(|value| session.scalar(&value?))
        .collect()
}

fn read_snapshot<'py>(
    session: &CursorSession<'py>,
    object: &Bound<'py, PyAny>,
) -> PyResult<CursorSnapshot> {
    let mut end_inputs: Vec<(Option<Scalar>, Option<Scalar>)> = Vec::new();
    for pair in object.getattr("upstream_end_inputs")?.try_iter()? {
        let pair = pair?;
        end_inputs.push((
            optional_scalar(session, &pair.get_item(0)?)?,
            optional_scalar(session, &pair.get_item(1)?)?,
        ));
    }
    Ok(CursorSnapshot {
        target_max: optional_scalar(session, &object.getattr("target_max")?)?,
        upstream_mins: scalars(session, object, "upstream_mins")?,
        upstream_maxes: scalars(session, object, "upstream_maxes")?,
        terminal_starts: scalars(session, object, "upstream_terminal_starts")?,
        terminal_ends: scalars(session, object, "upstream_terminal_ends")?,
        availability_ends: scalars(session, object, "upstream_availability_ends")?,
        any_input: object.getattr("cursor_watermark_mode")?.eq("any")?,
        end_inputs,
    })
}

fn duration(value: &Bound<'_, PyAny>) -> PyResult<Option<DurationSpan>> {
    if value.is_none() {
        return Ok(None);
    }
    let class = imported(value.py(), MODELS, "Duration")?;
    let parsed = if value.is_instance(&class)? {
        value.clone()
    } else {
        class.call_method1("parse", (value,))?
    };
    if parsed.is_none() {
        return Ok(None);
    }
    let field = |name: &str| -> PyResult<i64> { parsed.getattr(name)?.extract() };
    Ok(Some(DurationSpan {
        months: field("years")? * 12 + field("months")?,
        days: field("days")?,
        hours: field("hours")?,
        minutes: field("minutes")?,
        seconds: field("seconds")?,
    }))
}

fn read_policy<'py>(
    session: &CursorSession<'py>,
    args: &KeywordArguments<'py>,
) -> PyResult<ReplayPolicy> {
    let floor = args.value("cursor_start")?;
    let cursor_type = args.value("cursor_type")?;
    let floor =
        if floor.is_none() || !(cursor_type.eq("timestamp")? || cursor_type.eq("integer")?) {
            None
        } else if session.scalar_typed(&floor)? {
            Some(session.scalar(&floor)?)
        } else {
            try_parse(&floor, &cursor_type)?
                .map(|value| session.scalar(&value))
                .transpose()?
        };
    Ok(ReplayPolicy {
        floor,
        lookback: duration(&args.value("lookback")?)?,
        backfill: duration(&args.value("backfill_duration")?)?,
        has_backfill: !args.value("backfill_duration")?.is_none(),
        has_start_override: args.flag("has_start_override")?,
    })
}

#[pyfunction]
#[pyo3(signature = (**kwargs))]
fn apply_typed_cursor_replay_policy<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "apply_typed_cursor_replay_policy",
        kwargs,
        (
            &[
                "start",
                "end",
                "cursor_start",
                "cursor_type",
                "lookback",
                "backfill_duration",
                "has_start_override",
            ],
            &[],
        ),
    )?;
    let session = CursorSession::new(py)?;
    let cursor_type: Option<String> = args.value("cursor_type")?.extract()?;
    let start = session.scalar(&args.value("start")?)?;
    let end = session.scalar(&args.value("end")?)?;
    let policy = read_policy(&session, &args)?;
    let result = session.checked(replay_start(
        (&start, &end),
        &policy,
        &CursorKind {
            cursor_type: cursor_type.as_deref(),
            grain: None,
        },
        &session,
    ))?;
    session.python_scalar(&result)
}

fn required_scalar<'py>(
    session: &CursorSession<'py>,
    raw: &Bound<'py, PyAny>,
    cursor_type: &Bound<'py, PyAny>,
) -> PyResult<Scalar> {
    let Some(value) = try_parse(raw, cursor_type)? else {
        return Err(algebra_error(
            raw.py(),
            &format!("invalid cursor value: {}", raw.str()?),
        ));
    };
    session.scalar(&value)
}

#[pyfunction]
#[pyo3(signature = (**kwargs))]
fn compute_cursor_bounds<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "compute_cursor_bounds",
        kwargs,
        (
            &[
                "cursor_snapshot",
                "cursor_type",
                "cursor_start",
                "lookback",
                "backfill_duration",
                "start_cursor_override",
                "end_cursor_override",
                "is_microbatch",
            ],
            &["cursor_grain", "maximum_start_policy"],
        ),
    )?;
    let bounds_class = imported(py, MODELS, "CursorBounds")?;
    if args.flag("is_microbatch")? {
        let sentinel = imported(py, "sqlbuild.cursor_algebra.types", "BoundSentinel")?;
        return call_with(
            &bounds_class,
            &[
                ("start", sentinel.getattr("START")?),
                ("end", sentinel.getattr("END")?),
            ],
        );
    }
    let snapshot = args.value("cursor_snapshot")?;
    if !snapshot.getattr("watermarks_available")?.is_truthy()? {
        return Ok(py.None().into_bound(py));
    }
    let session = CursorSession::new(py)?;
    let cursor_type: Option<String> = args.value("cursor_type")?.extract()?;
    let grain = session.grain(&args.value("cursor_grain")?)?;
    let kind = CursorKind {
        cursor_type: cursor_type.as_deref(),
        grain,
    };
    let Some((mut start, mut end)) = session.checked(raw_bounds(
        &read_snapshot(&session, &snapshot)?,
        &kind,
        &session,
    ))?
    else {
        return Ok(py.None().into_bound(py));
    };
    let parse_type = string(py, cursor_type.as_deref().unwrap_or("timestamp"));
    let start_override = args.value("start_cursor_override")?;
    let end_override = args.value("end_cursor_override")?;
    if !start_override.is_none() {
        start = required_scalar(&session, &start_override, &parse_type)?;
    }
    if !end_override.is_none() {
        let value = required_scalar(&session, &end_override, &parse_type)?;
        end = session.checked(inclusive_to_exclusive(
            &value,
            if cursor_type.as_deref() == Some("integer") {
                None
            } else {
                Some(grain.unwrap_or(Grain::Second))
            },
        ))?;
    }
    let mut replay_args: Vec<(&str, Bound<'py, PyAny>)> = Vec::new();
    for key in [
        "cursor_start",
        "cursor_type",
        "lookback",
        "backfill_duration",
    ] {
        replay_args.push((key, args.value(key)?));
    }
    replay_args.extend([
        ("start", session.python_scalar(&start)?),
        ("end", session.python_scalar(&end)?),
        (
            "has_start_override",
            (!start_override.is_none())
                .into_pyobject(py)?
                .to_owned()
                .into_any(),
        ),
    ]);
    let replayed = call_with(
        &imported(py, "sqlbuild._native", "apply_typed_cursor_replay_policy")?,
        &replay_args,
    )?;
    let bounds = call_with(
        &bounds_class,
        &[("start", replayed), ("end", session.python_scalar(&end)?)],
    )?;
    let policy = args.value("maximum_start_policy")?;
    let policy = if policy.is_truthy()? {
        policy
    } else {
        imported(py, MODELS, "MaximumStartPolicyInputs")?.call0()?
    };
    let mut policy_args = vec![
        ("bounds", bounds),
        ("snapshot", snapshot),
        ("policy", policy),
        (
            "has_start_override",
            (!start_override.is_none())
                .into_pyobject(py)?
                .to_owned()
                .into_any(),
        ),
    ];
    for key in [
        "cursor_type",
        "cursor_grain",
        "cursor_start",
        "lookback",
        "backfill_duration",
    ] {
        policy_args.push((key, args.value(key)?));
    }
    call_with(
        &imported(py, MAXIMUM_START, "apply_maximum_start_policy")?,
        &policy_args,
    )
}

pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(compute_cursor_bounds, module)?)?;
    module.add_function(wrap_pyfunction!(apply_typed_cursor_replay_policy, module)?)
}
