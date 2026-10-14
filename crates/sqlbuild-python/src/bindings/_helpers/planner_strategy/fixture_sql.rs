//! Adapter-bound rendering of fixture completion SQL.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::planner_fixtures::main::{
    empty_fixture_error::empty_fixture_error, empty_fixture_marker::empty_fixture_marker,
    render_completed::render_completed as native_render_completed, render_empty::render_empty,
};
use sqlbuild_analysis::planner_fixtures::models::{FixtureSqlInput, SuppliedProjection};

use crate::bindings::_helpers::boundary::panics::value_error;
use crate::bindings::_helpers::planner_strategy::fixture_values::columns;

#[pyfunction(name = "is_empty_fixture_query")]
pub(crate) fn fixture_marker(sql: &str) -> PyResult<bool> {
    empty_fixture_marker(sql).map_err(value_error)
}

#[pyfunction]
#[pyo3(signature = (*, sql, relation, adapter))]
pub(crate) fn complete_empty_fixture_sql(
    sql: &str,
    relation: &Bound<'_, PyAny>,
    adapter: &Bound<'_, PyAny>,
) -> PyResult<(String, Option<String>)> {
    if !fixture_marker(sql)? {
        return Ok((sql.into(), None));
    }
    let authoritative =
        !relation.is_none() && relation.getattr("authoritative_names")?.is_truthy()?;
    let metadata = if authoritative {
        columns(&relation.getattr("columns")?, false)?
    } else {
        Vec::new()
    };
    if let Some(error) = empty_fixture_error(authoritative, &metadata) {
        return Ok((sql.into(), Some(error)));
    }
    Ok((
        render_empty(&metadata, |name| {
            adapter
                .call_method1("render_identifier", (name,))?
                .extract::<String>()
        })?,
        None,
    ))
}

pub(crate) struct CompletionSql<'py, 'a> {
    pub(crate) sql: &'a str,
    pub(crate) inferred: Bound<'py, PyAny>,
    pub(crate) typed_nulls: Bound<'py, PyDict>,
    pub(crate) quoted_names: Bound<'py, PyAny>,
    pub(crate) completed: Bound<'py, PyAny>,
}

pub(crate) fn render_completed(
    input: CompletionSql<'_, '_>,
    adapter: &Bound<'_, PyAny>,
) -> PyResult<String> {
    let mut supplied: Vec<SuppliedProjection> = Vec::new();
    if !input.typed_nulls.is_empty() {
        for column in input.inferred.try_iter()? {
            let column = column?;
            let name = column.getattr("name")?;
            let folded = name.call_method0("casefold")?;
            supplied.push(SuppliedProjection {
                name: name.extract()?,
                quoted: input.quoted_names.contains(&folded)?,
                expected_type: input
                    .typed_nulls
                    .get_item(folded)?
                    .map(|value| value.extract())
                    .transpose()?,
            });
        }
    }
    native_render_completed(
        FixtureSqlInput {
            sql: input.sql,
            supplied: &supplied,
            typed_nulls: !input.typed_nulls.is_empty(),
            completed: &columns(&input.completed, false)?,
        },
        |name, exact| {
            adapter
                .call_method1(
                    if exact {
                        "render_exact_identifier"
                    } else {
                        "render_identifier"
                    },
                    (name,),
                )?
                .extract::<String>()
        },
    )
}

#[pyfunction]
#[pyo3(signature = (*, sql, inference, expected_types, adapter))]
pub(crate) fn complete_typed_null_columns(
    sql: &str,
    inference: &Bound<'_, PyAny>,
    expected_types: &Bound<'_, PyDict>,
    adapter: &Bound<'_, PyAny>,
) -> PyResult<String> {
    let py = inference.py();
    let typed_nulls = PyDict::new(py);
    for name in inference.getattr("null_literal_names")?.try_iter()? {
        let name = name?;
        if let Some(expected) = expected_types.get_item(&name)? {
            typed_nulls.set_item(name, expected)?;
        }
    }
    if typed_nulls.is_empty() {
        return Ok(sql.into());
    }
    render_completed(
        CompletionSql {
            sql,
            inferred: inference.getattr("columns")?,
            typed_nulls,
            quoted_names: inference.getattr("quoted_names")?,
            completed: pyo3::types::PyTuple::empty(py).into_any(),
        },
        adapter,
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(fixture_marker, module)?)?;
    module.add_function(wrap_pyfunction!(complete_empty_fixture_sql, module)?)?;
    module.add_function(wrap_pyfunction!(complete_typed_null_columns, module)?)
}
