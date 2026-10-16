//! Adapt existing Python query shape models to pure migration proofs.

use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, call_with};
use crate::bindings::_helpers::planner_migrations::errors::ProofError;
use crate::bindings::_helpers::records::ids::RecordId;
use crate::bindings::_helpers::records::registry;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyFrozenSet, PyTuple};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_analysis::planner_migrations::main::{query_shape, renames_explain_change as proof};
use sqlbuild_analysis::planner_migrations::models::{QueryProjection, QueryShape};

fn read_shape(shape: &Bound<'_, PyAny>) -> PyResult<QueryShape> {
    let mut projections: Vec<QueryProjection> = Vec::new();
    for item in shape.getattr("projections")?.try_iter()? {
        let item = item?;
        projections.push(QueryProjection {
            name: item.getattr("name")?.extract()?,
            expression: item.getattr("expression")?.extract()?,
            references: item.getattr("references")?.extract()?,
            passthrough: item.getattr("passthrough")?.extract()?,
        });
    }
    Ok(QueryShape {
        projections,
        body: shape.getattr("body")?.extract()?,
        alias_clauses: shape.getattr("alias_clauses")?.extract()?,
        positional: shape.getattr("positional")?.extract()?,
        input_relations: shape.getattr("input_relations")?.extract()?,
        local_input_columns: shape.getattr("local_input_columns")?.extract()?,
        clause_references: shape.getattr("clause_references")?.extract()?,
    })
}

/// Named projections of one plain SELECT, or None when unknowable.
#[pyfunction]
#[pyo3(signature = (*, query_sql, dialect))]
fn parse_query_shape<'py>(
    py: Python<'py>,
    query_sql: &str,
    dialect: Option<&str>,
) -> PyResult<Bound<'py, PyAny>> {
    let Some(shape) = query_shape::query_shape(
        query_sql,
        dialect
            .filter(|value| !value.is_empty())
            .unwrap_or("generic"),
    )
    .map_err(PyValueError::new_err)?
    else {
        return Ok(py.None().into_bound(py));
    };
    let mut projections: Vec<Bound<'py, PyAny>> = Vec::new();
    for item in shape.projections {
        projections.push(call_with(
            &registry::class(py, RecordId::QueryProjection)?,
            &[
                ("name", item.name.into_pyobject(py)?.into_any()),
                ("expression", item.expression.into_pyobject(py)?.into_any()),
                (
                    "references",
                    PyFrozenSet::new(py, item.references)?.into_any(),
                ),
                (
                    "passthrough",
                    item.passthrough.into_pyobject(py)?.to_owned().into_any(),
                ),
            ],
        )?);
    }
    let relations = match shape.input_relations {
        Some(relations) => PyTuple::new(py, relations)?.into_any(),
        None => py.None().into_bound(py),
    };
    call_with(
        &registry::class(py, RecordId::QueryShape)?,
        &[
            ("projections", PyTuple::new(py, projections)?.into_any()),
            ("body", shape.body.into_pyobject(py)?.into_any()),
            (
                "alias_clauses",
                shape.alias_clauses.into_pyobject(py)?.into_any(),
            ),
            (
                "positional",
                shape.positional.into_pyobject(py)?.to_owned().into_any(),
            ),
            ("input_relations", relations),
            (
                "local_input_columns",
                PyFrozenSet::new(py, shape.local_input_columns)?.into_any(),
            ),
            (
                "clause_references",
                PyFrozenSet::new(py, shape.clause_references)?.into_any(),
            ),
        ],
    )
}

pub(crate) fn explain(
    previous: &Bound<'_, PyAny>,
    current: &Bound<'_, PyAny>,
    renames: &Bound<'_, PyAny>,
    input_columns: &Bound<'_, PyAny>,
) -> PyResult<bool> {
    let mut pairs: Vec<(String, String)> = Vec::new();
    for item in renames.call_method0("items")?.try_iter()? {
        pairs.push(item?.extract::<(String, String)>()?);
    }
    proof::renames_explain_change(
        (&read_shape(previous)?, &read_shape(current)?),
        &pairs,
        |kind, name| {
            input_columns
                .call1((kind, name))
                .and_then(|columns| columns.extract())
                .map_err(ProofError)
        },
    )
    .map_err(|error| error.0)
}

/// Whether output renaming explains the whole query change.
#[pyfunction]
#[pyo3(signature = (**options))]
fn renames_explain_change(py: Python<'_>, options: Option<Bound<'_, PyDict>>) -> PyResult<bool> {
    let arguments = KeywordArguments::read(
        py,
        "renames_explain_change",
        options,
        (&["previous", "current", "renames", "input_columns"], &[]),
    )?;
    explain(
        &arguments.value("previous")?,
        &arguments.value("current")?,
        &arguments.value("renames")?,
        &arguments.value("input_columns")?,
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(parse_query_shape, module)?)?;
    module.add_function(wrap_pyfunction!(renames_explain_change, module)?)
}
