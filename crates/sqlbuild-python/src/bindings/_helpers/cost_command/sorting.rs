//! Python's stable `sorted` over cost records and resources, keyed by the requested metric.

use pyo3::exceptions::PyKeyError;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyCFunction, PyDict, PyDictMethods, PyInt, PyList, PyTuple, PyTupleMethods};
use sqlbuild_core::cost_command::constants::{HISTORY_METRIC_SORT_FIELDS, MISSING_METRIC_STATUSES};

use crate::bindings::_helpers::boundary::python_calls::imported;
use crate::bindings::_helpers::records::fields::field as native_field;

type SortKey = fn(&Bound<'_, PyAny>, &str) -> PyResult<Py<PyAny>>;

/// `sorted(items, key=lambda item: key(item, field), reverse=reverse)`.
fn sorted_with<'py>(
    py: Python<'py>,
    items: Vec<Bound<'py, PyAny>>,
    (key, field): (SortKey, &str),
    reverse: bool,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let field: String = field.to_owned();
    let function = move |arguments: &Bound<'_, PyTuple>,
                         _: Option<&Bound<'_, PyDict>>|
          -> PyResult<Py<PyAny>> { key(&arguments.get_item(0)?, &field) };
    let options: Bound<'py, PyDict> = PyDict::new(py);
    options.set_item("key", PyCFunction::new_closure(py, None, None, function)?)?;
    options.set_item("reverse", reverse)?;
    imported(py, "builtins", "sorted")?
        .call((PyList::new(py, items)?,), Some(&options))?
        .try_iter()?
        .collect()
}

fn attribute(item: &Bound<'_, PyAny>, path: &str) -> PyResult<Py<PyAny>> {
    let mut value: Bound<'_, PyAny> = item.clone();
    for name in path.split('.') {
        value = native_field(&value, name)?;
    }
    Ok(value.unbind())
}

fn history_value(record: &Bound<'_, PyAny>, field: &str) -> PyResult<Py<PyAny>> {
    let py: Python<'_> = record.py();
    match field {
        "completed" => attribute(record, "completed_at"),
        "cost" => attribute(record, "cost.estimated_usd"),
        "credits" => attribute(record, "cost.estimated_compute_credits"),
        "duration" => Ok(native_field(record, "completed_at")?
            .sub(native_field(record, "started_at")?)?
            .unbind()),
        "models" => Ok(PyInt::new(
            py,
            native_field(record, "cost")?.getattr("resources")?.len()?,
        )
        .into_any()
        .unbind()),
        "status" => attribute(record, "cost.status.value"),
        _ => Err(PyKeyError::new_err(field.to_owned())),
    }
}

fn resource_value(resource: &Bound<'_, PyAny>, field: &str) -> PyResult<Py<PyAny>> {
    let path: &str = match field {
        "cost" => "estimated_usd",
        "credits" => "estimated_compute_credits",
        "busy" => "attributed_seconds",
        "scanned" => "bytes_scanned",
        "model" => "resource_name",
        "warehouse" => "warehouse_name",
        _ => return Err(PyKeyError::new_err(field.to_owned())),
    };
    let py: Python<'_> = resource.py();
    Ok(PyTuple::new(
        py,
        [
            attribute(resource, path)?,
            attribute(resource, "resource_name")?,
            attribute(resource, "warehouse_name")?,
        ],
    )?
    .into_any()
    .unbind())
}

fn by_attribute(item: &Bound<'_, PyAny>, path: &str) -> PyResult<Py<PyAny>> {
    attribute(item, path)
}

/// Newest first with run ids as the tie-break, then stably by the field.
fn sort_partition<'py>(
    py: Python<'py>,
    records: Vec<Bound<'py, PyAny>>,
    field: &str,
    descending: bool,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let by_run_id = sorted_with(py, records, (by_attribute, "run_id"), false)?;
    let by_completion = sorted_with(py, by_run_id, (by_attribute, "completed_at"), true)?;
    sorted_with(py, by_completion, (history_value, field), descending)
}

/// History records by the field; metric sorts put runs without metrics last, newest first.
pub(crate) fn sort_history<'py>(
    py: Python<'py>,
    records: Vec<Bound<'py, PyAny>>,
    field: &str,
    descending: bool,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    if !HISTORY_METRIC_SORT_FIELDS.contains(&field) {
        return sort_partition(py, records, field, descending);
    }
    let mut available: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut missing: Vec<Bound<'py, PyAny>> = Vec::new();
    for record in records {
        let status: String = native_field(&record, "cost")?
            .getattr("status")?
            .getattr("value")?
            .extract()?;
        if MISSING_METRIC_STATUSES.contains(&status.as_str()) {
            missing.push(record);
        } else {
            available.push(record);
        }
    }
    let mut sorted: Vec<Bound<'py, PyAny>> = sort_partition(py, available, field, descending)?;
    let missing = sorted_with(py, missing, (by_attribute, "run_id"), false)?;
    sorted.extend(sorted_with(
        py,
        missing,
        (by_attribute, "completed_at"),
        true,
    )?);
    Ok(sorted)
}

/// Breakdown resources by the field, then resource and warehouse name.
pub(crate) fn sort_resources<'py>(
    py: Python<'py>,
    resources: Vec<Bound<'py, PyAny>>,
    field: &str,
    descending: bool,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    sorted_with(py, resources, (resource_value, field), descending)
}
