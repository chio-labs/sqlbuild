//! Boundary conversions for the column migration planner.

use crate::bindings::_helpers::analysis::model_reads;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::model_config::config_values::config_str as authored_config_str;
use crate::bindings::_helpers::planner_identity::hashing::model_definition_hash;
use crate::bindings::_helpers::planner_phases::objects::object;
use crate::bindings::_helpers::records::ids::{NativeItem, RecordId};
use crate::bindings::_helpers::records::registry;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString};

pub(super) fn text<'py>(py: Python<'py>, value: &str) -> Bound<'py, PyAny> {
    PyString::new(py, value).into_any()
}

pub(super) fn lower(value: &Bound<'_, PyAny>) -> PyResult<String> {
    value.call_method0("lower")?.extract()
}

pub(super) fn replace<'py>(
    value: &Bound<'py, PyAny>,
    fields: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    let kwargs = PyDict::new(value.py());
    for (name, field) in fields {
        kwargs.set_item(name, field)?;
    }
    imported(value.py(), "dataclasses", "replace")?.call((value,), Some(&kwargs))
}

pub(super) fn model<'py>(
    py: Python<'py>,
    name: RecordId,
    fields: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    call_with(&registry::class(py, name)?, fields)
}

pub(super) fn native<'py>(
    py: Python<'py>,
    name: impl Into<NativeItem>,
    fields: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    call_with(&registry::item(py, name)?, fields)
}

pub(super) fn config<'py>(model: &Bound<'py, PyAny>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    Ok(
        authored_config_str(&model.getattr("config")?.getattr("values")?, key)?
            .unwrap_or_else(|| model.py().None().into_bound(model.py())),
    )
}

pub(super) fn definition_hash<'py>(
    model: &Bound<'py, PyAny>,
    snapshot: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    object(
        model.py(),
        model_definition_hash(
            model.py(),
            &model_reads::name_object(model)?.extract::<String>()?,
            &model_reads::query_sql(model)?.extract::<String>()?,
            snapshot
                .getattr("column_dialect")?
                .extract::<Option<String>>()?
                .as_deref(),
        )?,
    )
}
