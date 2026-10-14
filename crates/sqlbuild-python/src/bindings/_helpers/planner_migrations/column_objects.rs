//! Boundary conversions for the column migration planner.

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::planner_migrations::constants::PLANNER_MODELS;
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
    name: &str,
    fields: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    call_with(&imported(py, PLANNER_MODELS, name)?, fields)
}

pub(super) fn native<'py>(
    py: Python<'py>,
    name: &str,
    fields: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    call_with(&imported(py, "sqlbuild._native", name)?, fields)
}

pub(super) fn config<'py>(model: &Bound<'py, PyAny>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    native(
        model.py(),
        "get_config_str",
        &[
            ("values", model.getattr("config")?.getattr("values")?),
            ("key", text(model.py(), key)),
        ],
    )
}

pub(super) fn definition_hash<'py>(
    model: &Bound<'py, PyAny>,
    snapshot: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    native(
        model.py(),
        "model_definition_hash",
        &[
            ("model_name", model.getattr("name")?),
            ("query_sql", model.getattr("query_sql")?),
            ("dialect", snapshot.getattr("column_dialect")?),
        ],
    )
}
