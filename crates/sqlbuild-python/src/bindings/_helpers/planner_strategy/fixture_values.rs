//! Fixture boundary records and adapter callbacks.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use sqlbuild_analysis::planner_fixtures::models::FixtureColumn;

pub(crate) const MODELS: &str = "sqlbuild.compiler.planner.models";

pub(crate) fn folded(value: &Bound<'_, PyAny>) -> PyResult<String> {
    value.call_method0("casefold")?.extract()
}

pub(crate) fn strings(values: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    values.try_iter()?.map(|value| value?.extract()).collect()
}

pub(crate) fn columns(values: &Bound<'_, PyAny>, inferred: bool) -> PyResult<Vec<FixtureColumn>> {
    values
        .try_iter()?
        .map(|value| {
            let value = value?;
            let name = value.getattr("name")?;
            Ok(FixtureColumn {
                name: name.extract()?,
                folded_name: folded(&name)?,
                sql_type: value.getattr("type")?.extract()?,
                nullable: if inferred {
                    None
                } else {
                    value.getattr("nullable")?.extract()?
                },
            })
        })
        .collect()
}

pub(crate) fn record<'py>(
    py: Python<'py>,
    name: &str,
    kwargs: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyAny>> {
    py.import(MODELS)?.getattr(name)?.call((), Some(kwargs))
}

pub(crate) fn metadata<'py>(
    py: Python<'py>,
    columns: &[FixtureColumn],
    authoritative: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let values = columns
        .iter()
        .map(|column| {
            let kwargs = PyDict::new(py);
            kwargs.set_item("name", &column.name)?;
            kwargs.set_item("type", &column.sql_type)?;
            kwargs.set_item("nullable", column.nullable)?;
            record(py, "FixtureColumnMetadata", &kwargs)
        })
        .collect::<PyResult<Vec<_>>>()?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("columns", PyTuple::new(py, values)?)?;
    kwargs.set_item("authoritative_names", authoritative)?;
    record(py, "FixtureRelationMetadata", &kwargs)
}

pub(crate) fn label(key: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(format!(
        "mock {} '{}'",
        key.get_item(0)?.getattr("value")?.extract::<String>()?,
        key.get_item(1)?.extract::<String>()?
    ))
}

pub(crate) fn diagnostic<'py>(
    key: &Bound<'py, PyAny>,
    message: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let kwargs = PyDict::new(key.py());
    kwargs.set_item("key", key)?;
    kwargs.set_item("message", message)?;
    record(key.py(), "RelationFixtureDiagnostic", &kwargs)
}
