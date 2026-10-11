//! Native audit, SQL test and SQL hook SQL checks against the closed model shapes.

use std::sync::Arc;

use pyo3::prelude::{
    Bound, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyRef, PyResult, Python,
};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::semantic_checks::main::resource_sql_diagnostics::resource_sql_diagnostics;
use sqlbuild_analysis::semantic_checks::models::{
    AuditSqlInput, HookModelInput, HookSqlInput, ResourceSqlDiagnostic, ResourceSqlFailure,
    ResourceSqlKind, ResourceSqlRequest, SqlTestSqlInput,
};

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::models::ProjectCatalog;
use crate::bindings::types::CompilerDetach;

const COMPILE_ERRORS_MODULE: &str = "sqlbuild.compiler.compile.exceptions";

type Shape = (String, Vec<(String, String)>);
/// `(name, definition, (target kind, target), column, built-in, path, contents, bodies, opts out, relations)`.
type AuditRow = (
    String,
    String,
    Option<(String, String)>,
    Option<String>,
    bool,
    String,
    String,
    Vec<(Option<String>, Option<String>)>,
    bool,
    Vec<String>,
);
/// `(name, expected models, path, contents, compiled body, authored body, opts out)`.
type TestRow = (String, Vec<String>, String, String, String, String, bool);
/// `(key, index, statement, hook path, definition, relations)`.
type HookRow = (
    String,
    usize,
    String,
    Option<String>,
    Option<String>,
    Vec<String>,
);
/// `(name, path, authored SQL, analysis disabled, hooks)`.
type ModelRow = (String, String, String, bool, Vec<HookRow>);
/// `(dialect, quoted ignore case, require analysis, shapes, audits, tests, models, hook files)`.
type RequestInput = (
    Option<String>,
    bool,
    bool,
    Vec<Shape>,
    Vec<AuditRow>,
    Vec<TestRow>,
    Vec<ModelRow>,
    Vec<(String, String)>,
);
/// `(kind, name, is error, code, message, path, span, note, help)`.
type DiagnosticRow = (
    &'static str,
    String,
    bool,
    String,
    String,
    String,
    (i64, i64, Option<i64>, Option<i64>),
    Option<String>,
    Option<String>,
);

fn audit(row: AuditRow) -> AuditSqlInput {
    let (
        name,
        definition_name,
        attached_target,
        attached_column,
        built_in,
        path,
        contents,
        bodies,
        opts_out,
        relations,
    ) = row;
    AuditSqlInput {
        name,
        definition_name,
        attached_target,
        attached_column,
        built_in,
        path,
        contents: Arc::from(contents),
        bodies,
        opts_out,
        relations,
    }
}

fn sql_test(row: TestRow) -> SqlTestSqlInput {
    let (name, expected_model_names, path, contents, sql_body, authored_body, opts_out) = row;
    SqlTestSqlInput {
        name,
        expected_model_names,
        path,
        contents: Arc::from(contents),
        sql_body,
        authored_body,
        opts_out,
    }
}

fn model(row: ModelRow) -> HookModelInput {
    let (name, path, authored_sql, analysis_disabled, hooks) = row;
    HookModelInput {
        name,
        path,
        authored_sql: Arc::from(authored_sql),
        analysis_disabled,
        hooks: hooks
            .into_iter()
            .map(
                |(key, index, statement, hook_path, definition, relations)| HookSqlInput {
                    key,
                    index,
                    statement,
                    hook_path,
                    definition,
                    relations,
                },
            )
            .collect(),
    }
}

fn request(input: RequestInput) -> ResourceSqlRequest {
    let (dialect, quoted_ignore_case, require_sql_analysis, shapes, audits, tests, models, files) =
        input;
    ResourceSqlRequest {
        dialect,
        quoted_ignore_case,
        require_sql_analysis,
        shapes,
        audits: audits.into_iter().map(audit).collect(),
        sql_tests: tests.into_iter().map(sql_test).collect(),
        models: models.into_iter().map(model).collect(),
        hook_files: files
            .into_iter()
            .map(|(path, contents)| (path, Arc::from(contents)))
            .collect(),
    }
}

fn row(diagnostic: ResourceSqlDiagnostic) -> DiagnosticRow {
    let kind = match diagnostic.kind {
        ResourceSqlKind::Audit => "audit",
        ResourceSqlKind::SqlTest => "sql_test",
        ResourceSqlKind::Model => "model",
    };
    (
        kind,
        diagnostic.resource_name,
        diagnostic.is_error,
        diagnostic.code,
        diagnostic.message,
        diagnostic.path,
        diagnostic.span,
        diagnostic.note,
        diagnostic.help,
    )
}

fn failure_error(py: Python<'_>, failure: ResourceSqlFailure) -> PyResult<PyErr> {
    Ok(match failure {
        ResourceSqlFailure::CursorIntrinsic(message) => PyErr::from_value(
            py.import(COMPILE_ERRORS_MODULE)?
                .getattr("CompileInputError")?
                .call1((message,))?,
        ),
        ResourceSqlFailure::Normalization(message) | ResourceSqlFailure::Internal(message) => {
            compiler_error(message)
        }
    })
}

/// Bind audit, SQL test and SQL hook bodies on `catalog` as Python's resource SQL checks do.
#[pyfunction]
fn resource_sql_diagnostic_rows(
    py: Python<'_>,
    catalog: PyRef<'_, ProjectCatalog>,
    input: RequestInput,
) -> PyResult<Vec<DiagnosticRow>> {
    let request = request(input);
    let catalog = &catalog.inner;
    let outcome = py
        .compiler_detach(|| Ok(resource_sql_diagnostics(&request, catalog)))
        .map_err(compiler_error)?;
    match outcome {
        Ok(diagnostics) => Ok(diagnostics.into_iter().map(row).collect()),
        Err(failure) => Err(failure_error(py, failure)?),
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(resource_sql_diagnostic_rows, module)?)
}
