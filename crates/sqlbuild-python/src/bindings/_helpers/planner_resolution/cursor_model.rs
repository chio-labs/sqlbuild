//! Model cursor orchestration over live warehouse snapshot facts.

use crate::bindings::_helpers::analysis::model_reads;
use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, call_with};
use crate::bindings::_helpers::model_config::config_values::{
    config_cursor_bound, config_str as authored_config_str,
};
use crate::bindings::_helpers::native_host::adapter::AdapterHost;
use crate::bindings::_helpers::native_host::executor::ExecutorHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::planner_resolution::constants::CURSOR_START;
use crate::bindings::_helpers::planner_resolution::cursor_policies::{
    future_cursor_config, start_cursor_config,
};
use crate::bindings::_helpers::planner_resolution::values::string;
use crate::bindings::_helpers::records::ids::{ErrorId, NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::PyDict;
use pyo3::{IntoPyObject, PyErr, pyfunction, wrap_pyfunction};

fn config<'py>(model: &Bound<'py, PyAny>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    let values: Bound<'py, PyAny> = model.getattr("config")?.getattr("values")?;
    let value: Option<Bound<'py, PyAny>> = if key == CURSOR_START {
        config_cursor_bound(&values, key)?
    } else {
        authored_config_str(&values, key)?
    };
    Ok(value.unwrap_or_else(|| model.py().None().into_bound(model.py())))
}

fn unbounded(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    let sentinel = host::entry(py, ExecutorHost::BoundSentinel)?;
    call_with(
        &registry::class(py, RecordId::CursorBounds)?,
        &[
            ("start", sentinel.getattr("START")?),
            ("end", sentinel.getattr("END")?),
        ],
    )
}

fn destination_exists(model: &Bound<'_, PyAny>, snapshot: &Bound<'_, PyAny>) -> PyResult<bool> {
    let relation = snapshot
        .getattr("existing_relations")?
        .call_method1("get", (model_reads::name_object(model)?,))?;
    if relation.is_none() {
        return Ok(false);
    }
    let destination = model_reads::destination(model)?;
    let key = call_with(
        &host::entry(model.py(), AdapterHost::RelationLookup)?.getattr("key")?,
        &[
            ("database", destination.getattr("database")?),
            ("schema", destination.getattr("schema")?),
            ("name", destination.getattr("name")?),
        ],
    )?;
    relation.getattr("identity")?.eq(key)
}

fn history_redirected(model: &Bound<'_, PyAny>, snapshot: &Bound<'_, PyAny>) -> PyResult<bool> {
    let target = snapshot.getattr("target_relation")?;
    Ok(!target.is_none()
        && target.ne(model_reads::destination(model)?.getattr("qualified_name")?)?)
}

#[pyfunction]
#[pyo3(signature = (**kwargs))]
pub(crate) fn compute_model_cursor_bounds<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "compute_model_cursor_bounds",
        kwargs,
        (
            &[
                "model",
                "snapshot",
                "backfill",
                "full_refresh",
                "start_cursor_override",
                "end_cursor_override",
                "runtime_cursor_producer_names",
                "context",
            ],
            &["replaces_relation"],
        ),
    )?;
    let model = args.value("model")?;
    if !config(&model, "materialized")?.eq("incremental")? || config(&model, "cursor")?.is_none() {
        return Ok(py.None().into_bound(py));
    }
    let context = args.value("context")?;
    let incremental_mode = config(&model, "incremental_mode")?;
    let future_config = future_cursor_config(&model, &context.getattr("future_cursor_config")?)?;
    let start_config = start_cursor_config(&model, &context.getattr("start_cursor_config")?)?;
    if incremental_mode.eq("microbatch")? {
        return unbounded(py);
    }
    let cursor_type = config(&model, "cursor_type")?;
    let cursor_grain = config(&model, "cursor_grain")?;
    let start_override = args.value("start_cursor_override")?;
    let end_override = args.value("end_cursor_override")?;
    let bounded = call_with(
        &registry::native(py, NativeAttr::ResolveBoundedCursorOverride)?,
        &[
            ("start_cursor_override", start_override.clone()),
            ("end_cursor_override", end_override.clone()),
            ("cursor_type", cursor_type.clone()),
            ("cursor_grain", cursor_grain.clone()),
        ],
    )?;
    if !bounded.is_none() {
        return Ok(bounded);
    }
    let snapshot = args.value("snapshot")?;
    let mut cursor_snapshot = snapshot
        .getattr("cursor_snapshots")?
        .call_method1("get", (model_reads::name_object(&model)?,))?;
    let roles = call_with(
        &registry::native(py, NativeAttr::ResolveCursorInputRoles)?,
        &[("model", model.clone())],
    )?;
    let producers = args.value("runtime_cursor_producer_names")?;
    let mut runtime_owned = false;
    for name in roles.getattr("watermark_inputs")?.try_iter()? {
        if producers.contains(name?)? {
            runtime_owned = true;
            break;
        }
    }
    let full_refresh = args.flag("full_refresh")?;
    let replaces = args.flag("replaces_relation")?;
    if !full_refresh && !runtime_owned && !cursor_snapshot.is_none() {
        let empty = call_with(
            &registry::native(py, NativeAttr::CursorInputsWithoutRows)?,
            &[("cursor_snapshot", cursor_snapshot.clone())],
        )?
        .getattr("input_names")?;
        if empty.is_truthy()?
            && replaces
            && (destination_exists(&model, &snapshot)?
                || history_redirected(&model, &cursor_snapshot)?)
        {
            let refusal = call_with(
                &registry::native(py, NativeAttr::EmptyInputRebuildRefusal)?,
                &[
                    ("model_name", model_reads::name_object(&model)?),
                    ("input_names", empty.clone()),
                    ("cursor_type", cursor_type.clone()),
                ],
            )?;
            return Err(PyErr::from_value(call_with(
                &registry::error(py, ErrorId::PlannerInput)?,
                &[
                    ("message", refusal.get_item(0)?),
                    ("code", string(py, "S302")),
                    ("help", refusal.get_item(1)?),
                ],
            )?));
        }
        if empty.is_truthy()? {
            return call_with(
                &registry::native(py, NativeAttr::EmptyCursorWindow)?,
                &[
                    ("cursor_type", cursor_type),
                    ("cursor_start", config(&model, "cursor_start")?),
                ],
            );
        }
        if !cursor_snapshot
            .getattr("watermarks_available")?
            .is_truthy()?
        {
            let unreadable = cursor_snapshot.getattr("unreadable_input_names")?;
            let names = if unreadable.is_truthy()? {
                unreadable
            } else {
                cursor_snapshot.getattr("unavailable_watermark_tags")?
            };
            return Err(PyErr::from_value(call_with(
                &registry::native(py, NativeAttr::UnreadableCursorInputsError)?,
                &[
                    ("model_name", model_reads::name_object(&model)?),
                    ("cursor_type", cursor_type),
                    ("input_names", names),
                ],
            )?));
        }
    }
    if full_refresh {
        return Ok(py.None().into_bound(py));
    }
    if runtime_owned {
        return unbounded(py);
    }
    if cursor_snapshot.is_none() {
        return Ok(py.None().into_bound(py));
    }
    if replaces {
        cursor_snapshot = call_with(
            &registry::native(py, NativeAttr::WithoutDestinationCursor)?,
            &[("cursor_snapshot", cursor_snapshot)],
        )?;
    }
    let backfill = args.value("backfill")?;
    let duration = if backfill.getattr("action")?.eq("bounded")? {
        backfill.getattr("duration")?
    } else {
        py.None().into_bound(py)
    };
    let policy = call_with(
        &registry::class(py, RecordId::MaximumStartPolicyInputs)?,
        &[
            ("config", start_config),
            ("invocation_time", context.getattr("invocation_time")?),
            (
                "incremental_strategy",
                config(&model, "incremental_strategy")?,
            ),
            ("incremental_mode", incremental_mode),
        ],
    )?;
    let bounds = call_with(
        &registry::native(py, NativeAttr::ComputeCursorBounds)?,
        &[
            ("cursor_snapshot", cursor_snapshot.clone()),
            ("cursor_type", cursor_type.clone()),
            ("cursor_start", config(&model, "cursor_start")?),
            ("lookback", config(&model, "lookback")?),
            ("backfill_duration", duration),
            ("start_cursor_override", start_override.clone()),
            ("end_cursor_override", end_override.clone()),
            (
                "is_microbatch",
                false.into_pyobject(py)?.to_owned().into_any(),
            ),
            ("cursor_grain", cursor_grain.clone()),
            ("maximum_start_policy", policy),
        ],
    )?;
    if bounds.is_none() {
        return Ok(bounds);
    }
    call_with(
        &registry::native(py, NativeAttr::ResolveFutureCursorSafety)?,
        &[
            ("bounds", bounds),
            ("cursor_type", cursor_type),
            ("cursor_grain", cursor_grain),
            ("config", future_config),
            ("invocation_time", context.getattr("invocation_time")?),
            (
                "has_complete_override",
                (!start_override.is_none() && !end_override.is_none())
                    .into_pyobject(py)?
                    .to_owned()
                    .into_any(),
            ),
            ("input_evidence", cursor_snapshot.getattr("input_evidence")?),
        ],
    )
}

pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(compute_model_cursor_bounds, module)?)
}
