//! The `assets` entries of execution-result documents.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyList};

use crate::bindings::_helpers::plan_output::safety::{future_cursor_safety, maximum_start_safety};
use crate::bindings::_helpers::plan_output::values::{any, dict, items, optional_enum_value};
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::fields::mapping_get;
use crate::bindings::_helpers::records::fields::mapping_items;
use crate::bindings::_helpers::result_output::projection::{Projection, rounded};

const FAILED_STATUS: &str = "failed";
const SQL_EVENT_KIND: &str = "sql";

/// A dictionary of the entries whose value is not `None`, in order.
pub(crate) fn without_none<'py>(
    py: Python<'py>,
    entries: Vec<(&str, Bound<'py, PyAny>)>,
) -> PyResult<Bound<'py, PyDict>> {
    dict(
        py,
        entries
            .into_iter()
            .filter(|(_, value)| !value.is_none())
            .collect(),
    )
}

/// `value or None`.
pub(crate) fn or_none<'py>(value: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    if value.is_truthy()? {
        return Ok(value);
    }
    Ok(value.py().None().into_bound(value.py()))
}

/// The qualified names of a plan's locations, or nothing without a plan.
fn targets<'py>(
    plan: Option<&Bound<'py, PyAny>>,
    field: &str,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let Some(plan) = plan else {
        return Ok(None);
    };
    let py: Python<'py> = plan.py();
    let names: Bound<'py, PyDict> = PyDict::new(py);
    for item in mapping_items(&native_field(plan, field)?)?.try_iter()? {
        let (name, location): (Bound<'py, PyAny>, Bound<'py, PyAny>) = item?.extract()?;
        names.set_item(name, native_field(&location, "qualified_name")?)?;
    }
    Ok(Some(names.into_any()))
}

/// `targets.get(name)`, or `None` without a plan.
fn target<'py>(
    py: Python<'py>,
    targets: Option<&Bound<'py, PyAny>>,
    name: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    match targets {
        Some(targets) => mapping_get(targets, name),
        None => Ok(py.None().into_bound(py)),
    }
}

fn last_recorded_sql<'py>(result: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = result.py();
    if !native_field(&native_field(result, "status")?, "value")?.eq(FAILED_STATUS)? {
        return Ok(py.None().into_bound(py));
    }
    let events: Vec<Bound<'py, PyAny>> = items(&native_field(result, "lifecycle_events")?)?;
    for event in events.iter().rev() {
        if native_field(&native_field(event, "kind")?, "value")?.eq(SQL_EVENT_KIND)? {
            return native_field(event, "content");
        }
    }
    Ok(py.None().into_bound(py))
}

/// The run type and accounting of a microbatch model result.
fn microbatch<'py>(result: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = result.py();
    let run_type: Bound<'py, PyAny> = native_field(result, "microbatch_run_type")?;
    if run_type.is_none() {
        return Ok(run_type);
    }
    let state: Bound<'py, PyDict> = dict(py, vec![("run_type", run_type)])?;
    for (key, field) in [
        ("strategy", "microbatch_strategy"),
        ("reason", "microbatch_plan_reason"),
    ] {
        let value: Bound<'py, PyAny> = native_field(result, field)?;
        if !value.is_none() {
            state.set_item(key, value)?;
        }
    }
    for (key, field) in [
        ("batch_count", "batch_count"),
        ("batch_size", "batch_size"),
        ("recovery_batch_count", "microbatch_recovery_batch_count"),
        ("known_gap_count", "microbatch_known_gap_count"),
        (
            "unaccounted_interval_count",
            "microbatch_unaccounted_interval_count",
        ),
        (
            "synthetic_completion_count",
            "microbatch_synthetic_completion_count",
        ),
        (
            "unknown_fingerprint_count",
            "microbatch_unknown_fingerprint_count",
        ),
        ("contiguous_frontier", "microbatch_contiguous_frontier"),
        (
            "unaccounted_partition_policy",
            "microbatch_unaccounted_partition_policy",
        ),
        ("replay_requirement_id", "microbatch_replay_requirement_id"),
        (
            "required_model_version_hash",
            "microbatch_required_model_version_hash",
        ),
        (
            "physical_generation_id",
            "microbatch_physical_generation_id",
        ),
        ("concurrent_enabled", "microbatch_concurrent_enabled"),
        ("batch_concurrency", "microbatch_batch_concurrency"),
        ("global_concurrency", "microbatch_global_concurrency"),
        (
            "replay_requirement_state",
            "microbatch_replay_requirement_state",
        ),
    ] {
        state.set_item(key, native_field(result, field)?)?;
    }
    let intervals: Bound<'py, PyList> = PyList::empty(py);
    for interval in items(&native_field(result, "microbatch_accounting_intervals")?)? {
        let fields: Vec<(&str, Bound<'py, PyAny>)> = [
            "partition_start",
            "partition_end",
            "accounting_status",
            "fingerprint_status",
            "model_version_hash",
            "completion_type",
            "event_id",
        ]
        .into_iter()
        .map(|field| Ok((field, native_field(&interval, field)?)))
        .collect::<PyResult<_>>()?;
        pyo3::types::PyListMethods::append(&intervals, dict(py, fields)?)?;
    }
    state.set_item("intervals", intervals)?;
    let limit: Bound<'py, PyAny> = native_field(result, "microbatch_limit")?;
    if !limit.is_none() {
        state.set_item("limit", limit)?;
        state.set_item("count", native_field(result, "microbatch_limit_count")?)?;
        state.set_item(
            "action",
            optional_enum_value(&native_field(result, "microbatch_limit_action")?)?,
        )?;
        state.set_item("warning", native_field(result, "microbatch_limit_warning")?)?;
    }
    Ok(state.into_any())
}

fn value<'py>(result: &Bound<'py, PyAny>, field: &str) -> PyResult<Bound<'py, PyAny>> {
    native_field(&native_field(result, field)?, "value")
}

/// `<field>.value` when it is set.
fn optional_value<'py>(result: &Bound<'py, PyAny>, field: &str) -> PyResult<Bound<'py, PyAny>> {
    let value: Bound<'py, PyAny> = native_field(result, field)?;
    if !value.is_truthy()? {
        return Ok(value.py().None().into_bound(value.py()));
    }
    native_field(&value, "value")
}

fn model_asset<'py>(
    projection: &Projection<'py>,
    result: &Bound<'py, PyAny>,
    targets: Option<&Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = result.py();
    let name: Bound<'py, PyAny> = native_field(result, "model_name")?;
    let planned: Bound<'py, PyAny> = target(py, targets, &name)?;
    let empty_inputs: Bound<'py, PyAny> =
        PyList::new(py, items(&native_field(result, "empty_cursor_inputs")?)?)?.into_any();
    without_none(
        py,
        vec![
            ("kind", any(py, "model")?),
            ("name", name),
            ("status", value(result, "status")?),
            (
                "duration_ms",
                projection.result_duration(result, &native_field(result, "duration_ms")?)?,
            ),
            (
                "target",
                if planned.is_truthy()? {
                    planned
                } else {
                    native_field(result, "promoted_relation")?
                },
            ),
            (
                "staging_relation",
                native_field(result, "staging_relation")?,
            ),
            ("failed_phase", optional_value(result, "failed_phase")?),
            ("skip_mode", optional_value(result, "skip_mode")?),
            ("skip_reason", native_field(result, "skip_reason")?),
            ("error_code", native_field(result, "error_code")?),
            ("error_help", native_field(result, "error_help")?),
            ("error_message", native_field(result, "error_message")?),
            ("failed_sql", native_field(result, "failed_sql")?),
            ("last_recorded_sql", last_recorded_sql(result)?),
            ("warnings", native_field(result, "warning_messages")?),
            ("empty_cursor_inputs", or_none(empty_inputs)?),
            (
                "waiting_on_empty_inputs",
                or_none(native_field(result, "waiting_on_empty_inputs")?)?,
            ),
            (
                "future_cursor_safety",
                future_cursor_safety(&native_field(result, "future_cursor_safety")?)?,
            ),
            (
                "maximum_start_safety",
                maximum_start_safety(&native_field(result, "maximum_start_safety")?)?,
            ),
            ("microbatch", microbatch(result)?),
        ],
    )
}

/// Model result assets, with plan targets when a plan is given.
pub(crate) fn model_assets<'py>(
    projection: &Projection<'py>,
    results: &[Bound<'py, PyAny>],
    plan: Option<&Bound<'py, PyAny>>,
) -> PyResult<Vec<Bound<'py, PyDict>>> {
    let targets: Option<Bound<'py, PyAny>> = targets(plan, "model_locations")?;
    let mut assets: Vec<Bound<'py, PyDict>> = Vec::new();
    for result in results {
        if projection.terminal_recorded(result)? {
            assets.push(model_asset(projection, result, targets.as_ref())?);
        }
    }
    Ok(assets)
}

/// Seed result assets, with plan targets and reasons when a plan is given.
pub(crate) fn seed_assets<'py>(
    projection: &Projection<'py>,
    results: &[Bound<'py, PyAny>],
    plan: Option<&Bound<'py, PyAny>>,
) -> PyResult<Vec<Bound<'py, PyDict>>> {
    let targets: Option<Bound<'py, PyAny>> = targets(plan, "seed_locations")?;
    let reasons: Option<Bound<'py, PyAny>> = match plan {
        Some(plan) => {
            let reasons: Bound<'py, PyDict> = PyDict::new(plan.py());
            for entry in items(&native_field(plan, "seed_entries")?)? {
                reasons.set_item(native_field(&entry, "name")?, value(&entry, "reason")?)?;
            }
            Some(reasons.into_any())
        }
        None => None,
    };
    let mut assets: Vec<Bound<'py, PyDict>> = Vec::new();
    for result in results {
        if !projection.terminal_recorded(result)? {
            continue;
        }
        let py: Python<'py> = result.py();
        let name: Bound<'py, PyAny> = native_field(result, "seed_name")?;
        assets.push(without_none(
            py,
            vec![
                ("kind", any(py, "seed")?),
                ("name", name.clone()),
                ("status", value(result, "status")?),
                (
                    "duration_ms",
                    projection.result_duration(result, &native_field(result, "duration_ms")?)?,
                ),
                ("target", target(py, targets.as_ref(), &name)?),
                ("reason", target(py, reasons.as_ref(), &name)?),
                ("error_code", native_field(result, "error_code")?),
                ("error_help", native_field(result, "error_help")?),
                ("error_message", native_field(result, "error_message")?),
            ],
        )?);
    }
    Ok(assets)
}

/// Function result assets, with plan targets when a plan is given.
pub(crate) fn function_assets<'py>(
    projection: &Projection<'py>,
    results: &[Bound<'py, PyAny>],
    plan: Option<&Bound<'py, PyAny>>,
) -> PyResult<Vec<Bound<'py, PyDict>>> {
    let targets: Option<Bound<'py, PyAny>> = targets(plan, "function_locations")?;
    let mut assets: Vec<Bound<'py, PyDict>> = Vec::new();
    for result in results {
        if !projection.terminal_recorded(result)? {
            continue;
        }
        let py: Python<'py> = result.py();
        let name: Bound<'py, PyAny> = native_field(result, "function_name")?;
        assets.push(without_none(
            py,
            vec![
                ("kind", native_field(result, "function_kind")?),
                ("name", name.clone()),
                ("status", value(result, "status")?),
                (
                    "duration_ms",
                    projection.result_duration(result, &native_field(result, "duration_ms")?)?,
                ),
                ("target", target(py, targets.as_ref(), &name)?),
                ("error_code", native_field(result, "error_code")?),
                ("error_help", native_field(result, "error_help")?),
                ("error_message", native_field(result, "error_message")?),
                ("warnings", native_field(result, "warning_messages")?),
            ],
        )?);
    }
    Ok(assets)
}

/// Source and loader load result assets.
pub(crate) fn load_assets<'py>(
    projection: &Projection<'py>,
    results: &[Bound<'py, PyAny>],
) -> PyResult<Vec<Bound<'py, PyDict>>> {
    let mut assets: Vec<Bound<'py, PyDict>> = Vec::new();
    for result in results {
        if !projection.terminal_recorded(result)? {
            continue;
        }
        let py: Python<'py> = result.py();
        assets.push(without_none(
            py,
            vec![
                ("kind", value(result, "resource_kind")?),
                ("name", native_field(result, "source_name")?),
                ("status", value(result, "status")?),
                (
                    "duration_ms",
                    projection.result_duration(result, &native_field(result, "duration_ms")?)?,
                ),
                ("target", native_field(result, "target")?),
                (
                    "staging_relation",
                    native_field(result, "staging_relation")?,
                ),
                ("loader", native_field(result, "loader_name")?),
                ("rows_loaded", native_field(result, "rows_loaded")?),
                ("skip_mode", optional_value(result, "skip_mode")?),
                ("skip_reason", native_field(result, "skip_reason")?),
                ("error_message", native_field(result, "error_message")?),
                (
                    "warnings",
                    or_none(native_field(result, "warning_messages")?)?,
                ),
            ],
        )?);
    }
    Ok(assets)
}

/// Python node result assets.
pub(crate) fn python_node_assets<'py>(
    projection: &Projection<'py>,
    results: &[Bound<'py, PyAny>],
) -> PyResult<Vec<Bound<'py, PyDict>>> {
    let mut assets: Vec<Bound<'py, PyDict>> = Vec::new();
    for result in results {
        if !projection.terminal_recorded(result)? {
            continue;
        }
        let py: Python<'py> = result.py();
        assets.push(without_none(
            py,
            vec![
                ("kind", value(result, "kind")?),
                ("name", native_field(result, "node_name")?),
                ("status", value(result, "status")?),
                ("metadata", native_field(result, "metadata")?),
                ("materialized", native_field(result, "materialized")?),
                ("skip_mode", optional_value(result, "skip_mode")?),
                ("skip_reason", native_field(result, "skip_reason")?),
                ("error_message", native_field(result, "error_message")?),
                (
                    "warnings",
                    or_none(native_field(result, "warning_messages")?)?,
                ),
            ],
        )?);
    }
    Ok(assets)
}

/// One clone item asset under its resource type.
pub(crate) fn clone_asset<'py>(
    projection: &Projection<'py>,
    item: &Bound<'py, PyAny>,
    resource_type: &str,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = item.py();
    let name: String = native_field(item, "name")?.extract()?;
    let seconds: Bound<'py, PyAny> = native_field(item, "duration_seconds")?;
    let fallback: Option<f64> = if seconds.is_none() {
        None
    } else {
        Some(seconds.extract::<f64>()? * 1000.0)
    };
    let duration: Option<f64> =
        projection.resource_duration((&name, &format!("{resource_type}:{name}")), fallback)?;
    without_none(
        py,
        vec![
            ("kind", any(py, resource_type)?),
            ("name", any(py, name)?),
            ("status", value(item, "status")?),
            ("action", value(item, "action")?),
            (
                "duration_ms",
                match duration {
                    Some(duration) => rounded(py, duration)?,
                    None => py.None().into_bound(py),
                },
            ),
            ("origin_relation", native_field(item, "origin_relation")?),
            ("target", native_field(item, "destination_relation")?),
            ("message", native_field(item, "message")?),
        ],
    )
}
