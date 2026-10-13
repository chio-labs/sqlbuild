//! Python's per-query column analysis outside the session, run natively.

use pyo3::prelude::{Bound, Py, PyAny, PyModule, PyModuleMethods, PyRef, PyResult, Python};
use pyo3::types::PyDict;
use pyo3::{PyErr, pyfunction, wrap_pyfunction};
use sqlbuild_analysis::assembly::analysis_session::errors::QueryColumnsFailure;
use sqlbuild_analysis::assembly::analysis_session::main::projection_facts::projection_facts;
use sqlbuild_analysis::assembly::analysis_session::main::query_columns::query_columns;
use sqlbuild_analysis::assembly::analysis_session::models::{
    ColumnFact, ProjectionFacts, QueryColumns, QueryColumnsInput, QueryColumnsMode,
    QueryColumnsRequest,
};
use sqlbuild_analysis::assembly::analysis_session::types::{Pairs, Shapes};
use sqlbuild_core::panics::main::native_failure::native_failure;

use crate::bindings::_helpers::analysis_session::nullability_rules::{
    RuleFailure, nullability_callback, raised,
};
use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::models::ProjectCatalog;
use crate::bindings::types::CompilerDetach;

const QUERY_COLUMNS_CONTEXT: &str = "native query column analysis";
const PROJECTION_FACTS_CONTEXT: &str = "native fixture projection facts";

/// `(sql, placeholders, analysis names, lineage references, recover CTE facts, mode)`.
pub(crate) type QueryRow = (
    String,
    Pairs,
    Vec<String>,
    Vec<(String, String, String)>,
    bool,
    String,
);
/// `(dialect, return types, rules, types, nullability, queries, normalization dialect)`.
type RequestRow = (String, Pairs, Pairs, Shapes, Shapes, Vec<QueryRow>, String);
/// `([(name, type)], NULL literal names, quoted names)`.
type ProjectionFactsRow = (Vec<(String, String)>, Vec<String>, Vec<String>);
/// `(succeeded, [(name, type, nullability)] or None, has star)`.
pub(crate) type ColumnsRow = (bool, Option<Vec<(String, Option<String>, String)>>, bool);

/// Each query's columns, as Python's analysis outside the session inferred them.
#[pyfunction]
#[pyo3(signature = (catalog, request, adapter_rules=None))]
pub(crate) fn infer_query_columns(
    py: Python<'_>,
    catalog: Option<PyRef<'_, ProjectCatalog>>,
    request: RequestRow,
    adapter_rules: Option<(Py<PyDict>, Py<PyAny>)>,
) -> PyResult<Vec<ColumnsRow>> {
    let (
        dialect,
        function_return_types,
        nullability_rules,
        types,
        nullability,
        queries,
        normalization_dialect,
    ) = request;
    let queries: Vec<QueryColumnsInput> = queries
        .into_iter()
        .map(query_input)
        .collect::<Result<_, String>>()
        .map_err(|reason| compiler_error(native_failure(QUERY_COLUMNS_CONTEXT, &reason)))?;
    let rule_failure: RuleFailure = RuleFailure::default();
    let request = QueryColumnsRequest {
        dialect,
        normalization_dialect,
        function_return_types,
        nullability_rules: Some(nullability_rules),
        nullability_callback: adapter_rules.map(|(rules, nullability)| {
            nullability_callback(rules, nullability, rule_failure.clone())
        }),
        types,
        nullability,
        queries,
    };
    let catalog = catalog.as_ref().map(|catalog| &catalog.inner);
    let columns = py.compiler_detach(|| Ok(query_columns(catalog, &request)));
    if let Some(error) = raised(&rule_failure) {
        return Err(error);
    }
    Ok(columns
        .map_err(|reason| compiler_error(native_failure(QUERY_COLUMNS_CONTEXT, &reason)))?
        .map_err(query_columns_error)?
        .into_iter()
        .map(columns_row)
        .collect())
}

/// A normalization rejection as Python's `ValueError`; anything else as an internal failure.
pub(crate) fn query_columns_error(failure: QueryColumnsFailure) -> PyErr {
    match failure {
        QueryColumnsFailure::Normalization(message) => compiler_error(message),
        QueryColumnsFailure::Internal(reason) => {
            compiler_error(native_failure(QUERY_COLUMNS_CONTEXT, &reason))
        }
    }
}

fn query_input(row: QueryRow) -> Result<QueryColumnsInput, String> {
    let (sql, placeholders, analysis_names, lineage_references, recover_cte_facts, mode) = row;
    let mode: QueryColumnsMode = match mode.as_str() {
        "batch" => QueryColumnsMode::Batch,
        "reanalysis" => QueryColumnsMode::Reanalysis,
        "parse" => QueryColumnsMode::Parse,
        "legacy" => QueryColumnsMode::Legacy,
        _ => return Err("an unknown query column analysis mode".to_owned()),
    };
    Ok(QueryColumnsInput {
        sql,
        placeholders,
        analysis_names,
        lineage_references,
        recover_cte_facts,
        mode,
    })
}

fn columns_row(columns: QueryColumns) -> ColumnsRow {
    (
        columns.succeeded,
        columns
            .columns
            .map(|columns| columns.into_iter().map(column_row).collect()),
        columns.has_star,
    )
}

/// Python's `_simple_projection_facts`: `(types, NULL literal names, quoted names)`, casefolded.
#[pyfunction]
fn fixture_projection_facts(
    py: Python<'_>,
    sql: &str,
    dialect: Option<&str>,
) -> PyResult<ProjectionFactsRow> {
    let facts: ProjectionFacts = py
        .compiler_detach(|| projection_facts(sql, dialect))
        .map_err(|reason| compiler_error(native_failure(PROJECTION_FACTS_CONTEXT, &reason)))?;
    Ok((facts.types, facts.null_literal_names, facts.quoted_names))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(fixture_projection_facts, module)?)?;
    Ok(())
}

fn column_row(column: ColumnFact) -> (String, Option<String>, String) {
    (column.name, column.data_type, column.nullability)
}
