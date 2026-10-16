//! The retention and table type a model inherits from its target and materialization defaults.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyBool, PyString, PyTuple};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};

const CONTRACT_MODELS_MODULE: &str = "sqlbuild._native";
const CONTRACT_TYPES_MODULE: &str = "sqlbuild._native";

/// `value`, unless it is `None`.
fn present(value: Bound<'_, PyAny>) -> Option<Bound<'_, PyAny>> {
    Some(value).filter(|value| !value.is_none())
}

fn source<'py>(py: Python<'py>, class: &str, member: &str) -> PyResult<Bound<'py, PyAny>> {
    imported(py, CONTRACT_TYPES_MODULE, class)?.getattr(member)
}

/// The `materialized` defaults entry, or `None` for a model without a table-backed materialization.
fn defaults_entry<'py>(
    materialized: &Bound<'py, PyAny>,
    materialization_defaults: &Bound<'py, PyAny>,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    if materialized.is_none() {
        return Ok(None);
    }
    let name: &Bound<'py, PyString> = materialized.downcast()?;
    materialization_defaults.getattr(name).map(Some)
}

fn retention<'py>(
    materialized: &Bound<'py, PyAny>,
    entry: Option<&Bound<'py, PyAny>>,
    target: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = materialized.py();
    let resolved: Bound<'py, PyAny> =
        imported(py, CONTRACT_MODELS_MODULE, "ResolvedTimeTravelRetention")?;
    let class = "TimeTravelRetentionSource";
    let mut policy: Option<(Bound<'py, PyAny>, &str)> = None;
    if let Some(entry) = entry {
        if !target.is_none() {
            policy = present(target.getattr("time_travel_retention")?).map(|p| (p, "TARGET"));
        }
        if let Some(found) = present(entry.getattr("time_travel_retention")?) {
            policy = Some((found, "MATERIALIZATION"));
        }
        if !target.is_none()
            && let Some(found) = present(
                target
                    .getattr("time_travel_retention_by_materialization")?
                    .call_method1("get", (materialized,))?,
            )
        {
            policy = Some((found, "TARGET"));
        }
    }
    let Some((policy, member)) = policy else {
        return resolved.call0();
    };
    call_with(
        &resolved,
        &[
            ("desired_days", policy.getattr("desired_days")?),
            ("unmanaged", policy.getattr("unmanaged")?),
            ("source", source(py, class, member)?),
        ],
    )
}

fn table_type<'py>(
    entry: Option<&Bound<'py, PyAny>>,
    target: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = target.py();
    let resolved: Bound<'py, PyAny> = imported(py, CONTRACT_MODELS_MODULE, "ResolvedTableType")?;
    let class = "TableTypeSource";
    let mut declared: Option<(Bound<'py, PyAny>, &str)> = None;
    if let Some(entry) = entry {
        if !target.is_none() {
            declared = present(target.getattr("default_table_type")?).map(|v| (v, "TARGET"));
        }
        if let Some(found) = present(entry.getattr("table_type")?) {
            declared = Some((found, "MATERIALIZATION"));
        }
    }
    let Some((value, member)) = declared else {
        return resolved.call0();
    };
    call_with(
        &resolved,
        &[
            ("value", value),
            ("source", source(py, class, member)?),
            ("declared", PyBool::new(py, true).to_owned().into_any()),
        ],
    )
}

/// The `(retention, table type)` a model with `materialized` inherits; `None` is not table-backed.
pub(crate) fn inherited_storage<'py>(
    materialized: &Bound<'py, PyAny>,
    materialization_defaults: &Bound<'py, PyAny>,
    target: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let entry: Option<Bound<'py, PyAny>> = defaults_entry(materialized, materialization_defaults)?;
    PyTuple::new(
        materialized.py(),
        [
            retention(materialized, entry.as_ref(), target)?,
            table_type(entry.as_ref(), target)?,
        ],
    )
}
