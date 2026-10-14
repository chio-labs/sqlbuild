//! Model cursor orchestration over live warehouse snapshot facts.

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::planner_resolution::constants::CURSOR_START;
use crate::bindings::_helpers::planner_resolution::values::{NATIVE_MODULE, string};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::PyDict;
use pyo3::{IntoPyObject, PyErr, pyfunction, wrap_pyfunction};

const MODELS: &str = "sqlbuild.compiler.planner.models";
const CURSOR: &str = "sqlbuild._native";
const POLICIES: &str = "sqlbuild.compiler.planner._helpers.resolve.cursor_policies";
const FUTURE: &str = "sqlbuild.compiler.planner.main.execution.future_cursor_safety";

fn config<'py>(model: &Bound<'py, PyAny>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    call_with(
        &imported(
            model.py(),
            NATIVE_MODULE,
            if key == CURSOR_START {
                "get_config_cursor_bound"
            } else {
                "get_config_str"
            },
        )?,
        &[
            ("values", model.getattr("config")?.getattr("values")?),
            ("key", string(model.py(), key)),
        ],
    )
}

fn unbounded(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    let sentinel = imported(py, "sqlbuild.cursor_algebra.types", "BoundSentinel")?;
    call_with(
        &imported(py, MODELS, "CursorBounds")?,
        &[
            ("start", sentinel.getattr("START")?),
            ("end", sentinel.getattr("END")?),
        ],
    )
}

fn destination_exists(model: &Bound<'_, PyAny>, snapshot: &Bound<'_, PyAny>) -> PyResult<bool> {
    let relation = snapshot
        .getattr("existing_relations")?
        .call_method1("get", (model.getattr("name")?,))?;
    if relation.is_none() {
        return Ok(false);
    }
    let destination = model.getattr("destination")?;
    let key = call_with(
        &imported(
            model.py(),
            "sqlbuild.adapter.contract.models",
            "RelationLookup",
        )?
        .getattr("key")?,
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
        && target.ne(model.getattr("destination")?.getattr("qualified_name")?)?)
}

#[pyfunction]
#[pyo3(signature = (**kwargs))]
fn compute_model_cursor_bounds<'py>(
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
    let future_config = call_with(
        &imported(py, POLICIES, "resolve_future_cursor_config")?,
        &[
            ("model", model.clone()),
            ("project_config", context.getattr("future_cursor_config")?),
        ],
    )?;
    let start_config = call_with(
        &imported(py, POLICIES, "resolve_start_cursor_config")?,
        &[
            ("model", model.clone()),
            ("project_config", context.getattr("start_cursor_config")?),
        ],
    )?;
    if incremental_mode.eq("microbatch")? {
        return unbounded(py);
    }
    let cursor_type = config(&model, "cursor_type")?;
    let cursor_grain = config(&model, "cursor_grain")?;
    let start_override = args.value("start_cursor_override")?;
    let end_override = args.value("end_cursor_override")?;
    let bounded = call_with(
        &imported(py, NATIVE_MODULE, "resolve_bounded_cursor_override")?,
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
        .call_method1("get", (model.getattr("name")?,))?;
    let roles = call_with(
        &imported(py, NATIVE_MODULE, "resolve_cursor_input_roles")?,
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
            &imported(py, CURSOR, "cursor_inputs_without_rows")?,
            &[("cursor_snapshot", cursor_snapshot.clone())],
        )?
        .getattr("input_names")?;
        if empty.is_truthy()?
            && replaces
            && (destination_exists(&model, &snapshot)?
                || history_redirected(&model, &cursor_snapshot)?)
        {
            let refusal = call_with(
                &imported(py, CURSOR, "empty_input_rebuild_refusal")?,
                &[
                    ("model_name", model.getattr("name")?),
                    ("input_names", empty.clone()),
                    ("cursor_type", cursor_type.clone()),
                ],
            )?;
            return Err(PyErr::from_value(call_with(
                &imported(
                    py,
                    "sqlbuild.compiler.planner.exceptions",
                    "PlannerInputError",
                )?,
                &[
                    ("message", refusal.get_item(0)?),
                    ("code", string(py, "S302")),
                    ("help", refusal.get_item(1)?),
                ],
            )?));
        }
        if empty.is_truthy()? {
            return call_with(
                &imported(py, CURSOR, "empty_cursor_window")?,
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
                &imported(py, CURSOR, "unreadable_cursor_inputs_error")?,
                &[
                    ("model_name", model.getattr("name")?),
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
            &imported(py, CURSOR, "without_destination_cursor")?,
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
        &imported(py, MODELS, "MaximumStartPolicyInputs")?,
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
        &imported(py, NATIVE_MODULE, "compute_cursor_bounds")?,
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
        &imported(py, FUTURE, "apply_future_cursor_safety")?,
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
