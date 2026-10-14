//! Compile-owned inputs of the semantic completion stage: shapes, requests and SQL test columns.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyRef, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyList, PyListMethods, PyString, PyTuple};

use crate::bindings::_helpers::analysis::binding_catalog::ignores_quoted_case;
use crate::bindings::_helpers::analysis::schema_request::{
    SchemaRequestParts, schema_validation_request,
};
use crate::bindings::_helpers::semantic_checks::resource_sql::resource_sql_diagnostics_of;
use crate::bindings::_helpers::semantic_shapes::declarations::{declared_types, function_names};
use crate::bindings::models::ProjectCatalog;

const NATIVE_MODULE: &str = "sqlbuild._native";
const ANALYSIS_MODELS_MODULE: &str = "sqlbuild.compiler.analysis_session.models";

/// The column names a metadata config value lists: a name, or the names of a list or tuple.
pub(crate) fn column_names(value: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    if value.is_instance_of::<PyString>() {
        return Ok(vec![value.extract()?]);
    }
    if !(value.is_instance_of::<PyList>() || value.is_instance_of::<PyTuple>()) {
        return Ok(Vec::new());
    }
    let mut names: Vec<String> = Vec::new();
    for item in value.try_iter()? {
        let item: Bound<'_, PyAny> = item?;
        if item.is_instance_of::<PyString>() {
            names.push(item.extract()?);
        }
    }
    Ok(names)
}

/// The inferred output column names of every model SQL test CTE body, by body.
pub(crate) fn sql_test_columns<'py>(
    project: &Bound<'py, PyAny>,
    profile: &Bound<'py, PyAny>,
    model_test_payload: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = project.py();
    let bodies: Bound<'py, PyDict> = PyDict::new(py);
    for test in project.getattr("sql_tests")?.try_iter()? {
        let payload: Bound<'py, PyAny> = test?.getattr("payload")?;
        if !payload.is_instance(model_test_payload)? {
            continue;
        }
        for cte in payload
            .getattr("authored_ctes")?
            .try_iter()?
            .chain(payload.getattr("expected_ctes")?.try_iter()?)
        {
            bodies.set_item(cte?.getattr("sql_body")?, py.None())?;
        }
    }
    let columns: Bound<'py, PyDict> = PyDict::new(py);
    if bodies.is_empty() {
        return Ok(columns);
    }
    let query_class: Bound<'py, PyAny> = py
        .import(ANALYSIS_MODELS_MODULE)?
        .getattr("NativeColumnQuery")?;
    let mut queries: Vec<Bound<'py, PyAny>> = Vec::with_capacity(bodies.len());
    for sql in bodies.keys() {
        let arguments: Bound<'py, PyDict> = PyDict::new(py);
        arguments.set_item("sql", sql)?;
        arguments.set_item("mode", "batch")?;
        arguments.set_item("recover_cte_facts", false)?;
        queries.push(query_class.call((), Some(&arguments))?);
    }
    let arguments: Bound<'py, PyDict> = PyDict::new(py);
    arguments.set_item("queries", PyTuple::new(py, queries)?)?;
    arguments.set_item("profile", profile)?;
    let analyses: Bound<'py, PyAny> = py
        .import(NATIVE_MODULE)?
        .getattr("infer_native_query_columns")?
        .call((), Some(&arguments))?;
    for (sql, analysis) in bodies.keys().iter().zip(analyses.try_iter()?) {
        let analysis: Bound<'py, PyAny> = analysis?;
        let mut names: Vec<Bound<'py, PyAny>> = Vec::new();
        let inferred: Bound<'py, PyAny> = analysis.getattr("columns")?;
        if !inferred.is_none() {
            for column in inferred.try_iter()? {
                names.push(column?.getattr("name")?);
            }
        }
        columns.set_item(sql, PyTuple::new(py, names)?)?;
    }
    Ok(columns)
}

/// Type recovery's request revalidating one failed model against `shapes`.
pub(crate) fn revalidation_request<'py>(
    project: &Bound<'py, PyAny>,
    model: &Bound<'py, PyAny>,
    shapes: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project.py();
    let dialect: Bound<'py, PyAny> = project.getattr("sql_analysis_dialect")?;
    let functions: Bound<'py, PyAny> = project.getattr("functions")?;
    let schema: Bound<'py, PyDict> = PyDict::new(py);
    for reference in model.getattr("references")?.try_iter()? {
        let name: Bound<'py, PyAny> = reference?.getattr("ref_name")?;
        let shape: Bound<'py, PyAny> = match shapes.get_item(&name)? {
            Some(shape) => shape,
            None => PyDict::new(py).into_any(),
        };
        schema.set_item(name, shape)?;
    }
    let ignores: bool = ignores_quoted_case(&project.getattr("effective_connection")?, &dialect)?;
    schema_validation_request(
        py,
        SchemaRequestParts {
            query_sql: model.getattr("query_sql")?.extract()?,
            placeholders: py.None().into_bound(py),
            known_functions: PyTuple::new(py, function_names(&functions)?)?.into_any(),
            known_types: PyTuple::new(py, declared_types(&functions, shapes.as_any())?)?.into_any(),
            dialect,
            schema: schema.into_any(),
            catalog: project.getattr("binding_catalog")?,
            quoted_identifiers_ignore_case: ignores,
        },
    )
}

/// The compile-time SQL checks of audits, SQL tests and SQL hooks.
pub(crate) fn resource_sql_diagnostics<'py>(
    project: &Bound<'py, PyAny>,
    shapes: &Bound<'py, PyAny>,
    profile: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let native: Bound<'py, PyAny> = project.getattr("binding_catalog")?.getattr("native")?;
    Ok(resource_sql_diagnostics_of(
        native.extract::<PyRef<'py, ProjectCatalog>>()?,
        project,
        shapes.cast::<PyDict>()?,
        profile,
    )?
    .into_any())
}
