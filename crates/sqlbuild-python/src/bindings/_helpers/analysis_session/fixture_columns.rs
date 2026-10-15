//! Fixture-column inference: columns plus explicitly untyped NULL projections.

use std::collections::HashMap;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::assembly::analysis_session::main::projection_facts::projection_facts;
use sqlbuild_analysis::assembly::analysis_session::models::ProjectionFacts;
use sqlbuild_core::panics::main::native_failure::native_failure;
use sqlbuild_core::text::main::python_casefold::python_casefold;

use crate::bindings::_helpers::analysis_session::query_columns::ColumnsRow;
use crate::bindings::_helpers::analysis_session::stage_functions::query_column_rows;
use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::types::CompilerDetach;

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";

const ANALYSIS_MODELS_MODULE: &str = "sqlbuild._native";
const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const LINEAGE_TYPES_MODULE: &str = "sqlbuild.compiler.lineage.types";
const PROJECTION_FACTS_CONTEXT: &str = "native fixture projection facts";
const LEGACY_MODE: &str = "legacy";

/// `infer_fixture_column_facts(*, query_sql, inference_profile)`: a `FixtureColumnInference`.
#[pyfunction]
#[pyo3(signature = (**request))]
fn infer_fixture_column_facts<'py>(
    request: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let request = Request::new("infer_fixture_column_facts", request)?;
    let py: Python<'py> = request.py();
    let query_sql: String = request.get("query_sql")?.extract()?;
    let profile: Bound<'py, PyAny> = request.get("inference_profile")?;
    let query: Bound<'py, PyDict> = PyDict::new(py);
    query.set_item("sql", &query_sql)?;
    query.set_item("mode", LEGACY_MODE)?;
    query.set_item("recover_cte_facts", false)?;
    let query: Bound<'py, PyAny> = py
        .import(ANALYSIS_MODELS_MODULE)?
        .getattr("NativeColumnQuery")?
        .call((), Some(&query))?;
    let empty: Bound<'py, PyAny> = PyDict::new(py).into_any();
    let rows: Vec<ColumnsRow> = query_column_rows(
        PyTuple::new(py, [query])?.as_any(),
        &profile,
        (&empty, &empty),
    )?;
    let Some((true, Some(columns), false)) = rows.into_iter().next() else {
        return Ok(py.None().into_bound(py));
    };
    let dialect: Option<String> = profile.getattr("sql_analysis_dialect")?.extract()?;
    let facts: ProjectionFacts = py
        .compiler_detach(|| projection_facts(&query_sql, dialect.as_deref()))
        .map_err(|reason| compiler_error(native_failure(PROJECTION_FACTS_CONTEXT, &reason)))?;
    let simple_types: HashMap<String, String> = facts.types.into_iter().collect();
    let column_class: Bound<'py, PyAny> = py
        .import(COMPILE_MODELS_MODULE)?
        .getattr("InferredColumn")?;
    let nullability_class: Bound<'py, PyAny> = py
        .import(LINEAGE_TYPES_MODULE)?
        .getattr("InferredNullability")?;
    let mut built: Vec<Bound<'py, PyAny>> = Vec::with_capacity(columns.len());
    for (name, data_type, nullability) in columns {
        let data_type: Option<String> = data_type
            .filter(|data_type| !data_type.is_empty())
            .or_else(|| simple_types.get(&python_casefold(&name)).cloned());
        let arguments: Bound<'py, PyDict> = PyDict::new(py);
        arguments.set_item("name", name)?;
        arguments.set_item("type", data_type)?;
        arguments.set_item("nullability", nullability_class.call1((nullability,))?)?;
        built.push(column_class.call((), Some(&arguments))?);
    }
    let arguments: Bound<'py, PyDict> = PyDict::new(py);
    arguments.set_item("columns", PyTuple::new(py, built)?)?;
    arguments.set_item(
        "null_literal_names",
        PyFrozenSet::new(py, facts.null_literal_names)?,
    )?;
    arguments.set_item("quoted_names", PyFrozenSet::new(py, facts.quoted_names)?)?;
    py.import(NATIVE_RECORDS_MODULE)?
        .getattr("FixtureColumnInference")?
        .call((), Some(&arguments))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(infer_fixture_column_facts, module)?)
}
