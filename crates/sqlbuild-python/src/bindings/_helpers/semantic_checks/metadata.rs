//! Native semantic metadata checks: config references, cursors, function calls and SQL tests.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyRef, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::semantic_checks::main::check_semantic_metadata::check_semantic_metadata;
use sqlbuild_analysis::semantic_checks::models::{
    AuditValue, MetadataAudit, MetadataFinding, MetadataFunction, MetadataModel, MetadataRequest,
    MetadataSource, MetadataSqlTest, ModelMetadataFindings,
};
use std::sync::Arc;

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::_helpers::semantic_checks::failures::semantic_error;
use crate::bindings::models::ProjectCatalog;
use crate::bindings::types::CompilerDetach;

/// `(key, names)` pairs in Python's order.
type NamesInput = Vec<(String, Vec<String>)>;
/// `(column, definition, expression, to, field, values as (kind, text))`.
type AuditInput = (
    Option<String>,
    String,
    Option<String>,
    String,
    String,
    Option<Vec<(String, String)>>,
);
/// `(name, query, authored, checked, functions, references, cursor inputs, cursor, type, audits)`.
type ModelInput = (
    String,
    String,
    String,
    bool,
    bool,
    NamesInput,
    NamesInput,
    Option<String>,
    Option<String>,
    Vec<AuditInput>,
);
/// `(dialect, quoted case, return types, functions, shapes, models, files, sources, SQL tests)`.
type RequestInput = (
    Option<String>,
    bool,
    Vec<(String, String)>,
    Vec<(String, Vec<(String, String)>)>,
    Vec<(String, Vec<(String, String)>)>,
    Vec<ModelInput>,
    Vec<String>,
    Vec<(String, Option<String>, usize)>,
    Vec<(usize, NamesInput)>,
);
/// `(code, message, line, column)`.
type ErrorRow = (&'static str, String, i64, i64);
/// `(code, message, line, column, is error)`.
type AuditRow = (String, String, i64, i64, bool);
/// `([(function, audit, reference findings)], source, SQL test findings, fallback types)`.
type OutcomeRow = (
    Vec<(Vec<ErrorRow>, Vec<AuditRow>, Vec<ErrorRow>)>,
    Vec<(usize, ErrorRow)>,
    Vec<(usize, ErrorRow, i64)>,
    Vec<String>,
);

/// Run the metadata checks on `catalog`'s analysis pool.
#[pyfunction]
fn check_semantic_metadata_rows(
    py: Python<'_>,
    catalog: PyRef<'_, ProjectCatalog>,
    request: RequestInput,
) -> PyResult<OutcomeRow> {
    let request = metadata_request(request)?;
    let catalog = &catalog.inner;
    let outcome = py
        .compiler_detach(|| Ok(check_semantic_metadata(&request, catalog)))
        .map_err(compiler_error)?
        .map_err(|failure| semantic_error(py, &failure))?;
    Ok((
        outcome.models.into_iter().map(model_rows).collect(),
        outcome
            .sources
            .into_iter()
            .map(|(index, error)| (index, error_row(error)))
            .collect(),
        outcome
            .sql_tests
            .into_iter()
            .map(|(index, error, end)| (index, error_row(error), end))
            .collect(),
        outcome.fallback_types,
    ))
}

fn error_row(error: MetadataFinding) -> ErrorRow {
    (error.code, error.message, error.line, error.column)
}

fn model_rows(errors: ModelMetadataFindings) -> (Vec<ErrorRow>, Vec<AuditRow>, Vec<ErrorRow>) {
    (
        errors.functions.into_iter().map(error_row).collect(),
        errors
            .audits
            .into_iter()
            .map(|finding| {
                (
                    finding.code,
                    finding.message,
                    finding.line,
                    finding.column,
                    finding.is_error,
                )
            })
            .collect(),
        errors.references.into_iter().map(error_row).collect(),
    )
}

fn metadata_request(
    (
        dialect,
        quoted_ignore_case,
        return_types,
        functions,
        shapes,
        models,
        files,
        sources,
        sql_tests,
    ): RequestInput,
) -> PyResult<MetadataRequest> {
    let files: Vec<Arc<str>> = files.into_iter().map(Arc::from).collect();
    let file = |index: usize| -> PyResult<Arc<str>> {
        files
            .get(index)
            .cloned()
            .ok_or_else(|| PyValueError::new_err("a metadata row names no file text"))
    };
    Ok(MetadataRequest {
        dialect,
        quoted_ignore_case,
        return_types,
        functions: functions
            .into_iter()
            .map(|(key, arguments)| MetadataFunction { key, arguments })
            .collect(),
        shapes,
        models: models.into_iter().map(metadata_model).collect(),
        sources: sources
            .into_iter()
            .map(|(name, cursor_column, index)| {
                Ok(MetadataSource {
                    name,
                    cursor_column,
                    contents: file(index)?,
                })
            })
            .collect::<PyResult<_>>()?,
        sql_tests: sql_tests
            .into_iter()
            .map(|(index, ctes)| {
                Ok(MetadataSqlTest {
                    contents: file(index)?,
                    ctes,
                })
            })
            .collect::<PyResult<_>>()?,
    })
}

fn metadata_model(
    (
        name,
        query_sql,
        authored_sql,
        checked,
        calls_functions,
        references,
        cursor_inputs,
        cursor,
        cursor_type,
        audits,
    ): ModelInput,
) -> MetadataModel {
    MetadataModel {
        name,
        query_sql,
        authored_sql,
        checked,
        calls_functions,
        references,
        cursor_inputs,
        cursor,
        cursor_type,
        audits: audits.into_iter().map(metadata_audit).collect(),
    }
}

fn audit_value((kind, text): (String, String)) -> AuditValue {
    match kind.as_str() {
        "null" => AuditValue::Null,
        "bool" => AuditValue::Bool(!text.is_empty()),
        "number" => AuditValue::Number(text),
        "text" => AuditValue::Text(text),
        _ => AuditValue::Other,
    }
}

fn metadata_audit(
    (column, definition, expression, target, field, values): AuditInput,
) -> MetadataAudit {
    MetadataAudit {
        column,
        definition,
        expression,
        target,
        field,
        values: values.map(|values| values.into_iter().map(audit_value).collect()),
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(check_semantic_metadata_rows, module)?)?;
    Ok(())
}
