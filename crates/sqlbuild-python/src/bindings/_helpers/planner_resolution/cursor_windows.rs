//! Empty-window decisions and snapshot grain conversion.

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::cursor::conversion::CursorSession;
use crate::bindings::_helpers::cursor::scalars::parse_value;
use crate::bindings::_helpers::planner_resolution::values::string;
use crate::bindings::_helpers::records::ids::{ErrorId, RecordId};
use crate::bindings::_helpers::records::registry;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_cursor::algebra::main::floor_to_grain::floor_to_grain;
use sqlbuild_cursor::planner::main::empty_inputs::empty_inputs;

#[pyfunction]
#[pyo3(signature = (*, empty_input_names, waits_for_every_input, inputs_with_rows, has_window_start))]
fn decide_empty_cursor_inputs<'py>(
    empty_input_names: &Bound<'py, PyAny>,
    waits_for_every_input: bool,
    inputs_with_rows: bool,
    has_window_start: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let py = empty_input_names.py();
    let class = registry::class(py, RecordId::EmptyCursorInputDecision)?;
    if !empty_input_names.is_truthy()?
        || !empty_inputs(waits_for_every_input, inputs_with_rows, has_window_start)
    {
        return class.call0();
    }
    call_with(
        &class,
        &[
            ("input_names", empty_input_names.clone()),
            (
                "waiting_on_empty_inputs",
                inputs_with_rows.into_pyobject(py)?.to_owned().into_any(),
            ),
        ],
    )
}

#[pyfunction]
#[pyo3(signature = (*, cursor_snapshot))]
fn cursor_inputs_without_rows<'py>(
    cursor_snapshot: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    if cursor_snapshot
        .getattr("unreadable_input_names")?
        .is_truthy()?
    {
        return registry::class(cursor_snapshot.py(), RecordId::EmptyCursorInputDecision)?.call0();
    }
    let rows = cursor_snapshot.getattr("upstream_maxes")?.is_truthy()?
        || cursor_snapshot
            .getattr("upstream_terminal_ends")?
            .is_truthy()?
        || cursor_snapshot
            .getattr("upstream_availability_ends")?
            .is_truthy()?;
    let start = !cursor_snapshot.getattr("target_max")?.is_none()
        || cursor_snapshot.getattr("upstream_mins")?.is_truthy()?
        || cursor_snapshot
            .getattr("upstream_terminal_starts")?
            .is_truthy()?;
    decide_empty_cursor_inputs(
        &cursor_snapshot.getattr("empty_input_names")?,
        !cursor_snapshot
            .getattr("cursor_watermark_mode")?
            .eq("any")?,
        rows,
        start,
    )
}

#[pyfunction]
#[pyo3(signature = (*, cursor_type, cursor_start))]
fn empty_cursor_window<'py>(
    cursor_type: &Bound<'py, PyAny>,
    cursor_start: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = cursor_type.py();
    let kind = if cursor_type.is_truthy()? {
        cursor_type.clone()
    } else {
        string(py, "timestamp")
    };
    let raw = if !cursor_start.is_none() {
        cursor_start.clone()
    } else if kind.eq("integer")? {
        string(py, "0")
    } else {
        string(py, "1970-01-01T00:00:00")
    };
    let mut bound = parse_value(&raw, &kind)?;
    if cursor_start.is_none() && !kind.eq("integer")? {
        bound = call_with(
            &registry::class(py, RecordId::TimestampValue)?,
            &[("value", bound.getattr("value")?)],
        )?;
    }
    call_with(
        &registry::class(py, RecordId::CursorBounds)?,
        &[("start", bound.clone()), ("end", bound)],
    )
}

#[pyfunction]
#[pyo3(signature = (*, cursor_type))]
fn cursor_window_override_flags(cursor_type: Option<&str>) -> String {
    let suffix = if cursor_type == Some("integer") {
        "int"
    } else {
        "ts"
    };
    format!("--start-cursor-{suffix} and --end-cursor-{suffix}")
}

#[pyfunction]
#[pyo3(signature = (*, model_name, input_names, cursor_type))]
fn empty_input_rebuild_refusal(
    model_name: &str,
    input_names: Vec<String>,
    cursor_type: Option<&str>,
) -> (String, String) {
    (
        format!(
            "model '{model_name}' was not rebuilt: its cursor inputs have no rows ({}), so rebuilding it now would leave it empty",
            input_names.join(", ")
        ),
        format!(
            "load the inputs first, or set the window explicitly with {}",
            cursor_window_override_flags(cursor_type)
        ),
    )
}

#[pyfunction]
#[pyo3(signature = (*, model_name, cursor_type, input_names))]
fn unreadable_cursor_inputs_error<'py>(
    py: Python<'py>,
    model_name: &str,
    cursor_type: Option<&str>,
    input_names: Vec<String>,
) -> PyResult<Bound<'py, PyAny>> {
    call_with(
        &registry::error(py, ErrorId::PlannerInput)?,
        &[
            (
                "message",
                string(
                    py,
                    &format!(
                        "model '{model_name}' cannot work out its cursor window: cursor bounds could not be read from {}",
                        input_names.join(", ")
                    ),
                ),
            ),
            ("code", string(py, "S302")),
            (
                "help",
                string(
                    py,
                    &format!(
                        "check that each input exists and has its cursor column (`sqb debug` checks the connection), or set the window explicitly with {}",
                        cursor_window_override_flags(cursor_type)
                    ),
                ),
            ),
        ],
    )
}

#[pyfunction]
#[pyo3(signature = (*, cursor_snapshot))]
fn without_destination_cursor<'py>(
    cursor_snapshot: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = cursor_snapshot.py();
    let kwargs = PyDict::new(py);
    for name in ["target_max", "physical_target_max", "target_eligible_max"] {
        kwargs.set_item(name, py.None())?;
    }
    imported(py, "dataclasses", "replace")?.call((cursor_snapshot,), Some(&kwargs))
}

#[pyfunction]
#[pyo3(signature = (*, cursor_type, downstream_grain, cursor_input_grains, microbatch_strategy=None))]
fn resolve_effective_timestamp_grain<'py>(
    cursor_type: &Bound<'py, PyAny>,
    downstream_grain: &Bound<'py, PyAny>,
    cursor_input_grains: &Bound<'py, PyAny>,
    microbatch_strategy: Option<&str>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = cursor_type.py();
    if !cursor_type.eq("timestamp")? {
        return Ok(py.None().into_bound(py));
    }
    let mut effective = if downstream_grain.is_truthy()? {
        downstream_grain.clone()
    } else {
        string(py, "second")
    };
    if microbatch_strategy == Some("watermark") {
        return Ok(effective);
    }
    let session = CursorSession::new(py)?;
    for value in cursor_input_grains.try_iter()? {
        let value = value?;
        let candidate = if value.is_truthy()? {
            value
        } else {
            string(py, "second")
        };
        if session.grain(&candidate)? > session.grain(&effective)? {
            effective = candidate;
        }
    }
    Ok(effective)
}

#[pyfunction]
#[pyo3(signature = (*, cursor_snapshot, cursor_type, effective_grain))]
fn normalize_cursor_snapshot_grain<'py>(
    cursor_snapshot: &Bound<'py, PyAny>,
    cursor_type: &Bound<'py, PyAny>,
    effective_grain: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    if !cursor_type.eq("timestamp")? || effective_grain.is_none() {
        return Ok(cursor_snapshot.clone());
    }
    let py = cursor_snapshot.py();
    let session = CursorSession::new(py)?;
    let grain = session.grain(effective_grain)?;
    let normalize = |value: Bound<'py, PyAny>| -> PyResult<Bound<'py, PyAny>> {
        if value.is_none() {
            return Ok(value);
        }
        session.python_scalar(&floor_to_grain(&session.scalar(&value)?, grain))
    };
    let kwargs = PyDict::new(py);
    for key in ["target_max", "target_eligible_max"] {
        kwargs.set_item(key, normalize(cursor_snapshot.getattr(key)?)?)?;
    }
    for key in ["upstream_mins", "upstream_maxes"] {
        let values = cursor_snapshot
            .getattr(key)?
            .try_iter()?
            .map(|value| normalize(value?))
            .collect::<PyResult<Vec<_>>>()?;
        kwargs.set_item(key, PyTuple::new(py, values)?)?;
    }
    let physical = cursor_snapshot.getattr("physical_target_max")?;
    kwargs.set_item(
        "physical_target_max",
        if physical.is_truthy()? {
            physical
        } else {
            cursor_snapshot.getattr("target_max")?
        },
    )?;
    let mut ends: Vec<(Bound<'py, PyAny>, Bound<'py, PyAny>)> = Vec::new();
    for pair in cursor_snapshot.getattr("upstream_end_inputs")?.try_iter()? {
        let pair = pair?;
        ends.push((normalize(pair.get_item(0)?)?, pair.get_item(1)?));
    }
    kwargs.set_item("upstream_end_inputs", PyTuple::new(py, ends)?)?;
    imported(py, "dataclasses", "replace")?.call((cursor_snapshot,), Some(&kwargs))
}

pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(decide_empty_cursor_inputs, module)?)?;
    module.add_function(wrap_pyfunction!(cursor_inputs_without_rows, module)?)?;
    module.add_function(wrap_pyfunction!(empty_cursor_window, module)?)?;
    module.add_function(wrap_pyfunction!(cursor_window_override_flags, module)?)?;
    module.add_function(wrap_pyfunction!(empty_input_rebuild_refusal, module)?)?;
    module.add_function(wrap_pyfunction!(unreadable_cursor_inputs_error, module)?)?;
    module.add_function(wrap_pyfunction!(without_destination_cursor, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_effective_timestamp_grain, module)?)?;
    module.add_function(wrap_pyfunction!(normalize_cursor_snapshot_grain, module)?)
}
