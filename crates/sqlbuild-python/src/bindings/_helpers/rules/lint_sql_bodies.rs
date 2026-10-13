//! Native SQL lint of prepared lint bodies, as Python lint violations.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_rules::lint_text::main::lint_sql_bodies::lint_sql_bodies;
use sqlbuild_rules::lint_text::models::{
    AuthoredDiagnostic, ExpansionSpan, LintSqlBody, LintSqlOptions,
};

use crate::bindings::_helpers::boundary::panics::value_error;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::types::CompilerDetach;

const LINT_MODELS_MODULE: &str = "sqlbuild.lint.models";
const LINT_TYPES_MODULE: &str = "sqlbuild.lint.types";
const NATIVE_ENGINE: &str = "native";

fn spans(passes: &Bound<'_, PyAny>) -> PyResult<Vec<Vec<ExpansionSpan>>> {
    passes.try_iter()?.map(|pass| pass_spans(&pass?)).collect()
}

fn pass_spans(pass: &Bound<'_, PyAny>) -> PyResult<Vec<ExpansionSpan>> {
    pass.try_iter()?
        .map(|span| {
            let span: Bound<'_, PyAny> = span?;
            Ok(ExpansionSpan {
                source_start: span.getattr("source_start")?.extract()?,
                source_end: span.getattr("source_end")?.extract()?,
                output_start: span.getattr("output_start")?.extract()?,
                output_end: span.getattr("output_end")?.extract()?,
            })
        })
        .collect()
}

/// Declared keys of the relations one body reads, by their neutralized sentinel.
fn relation_keys(
    body: &Bound<'_, PyAny>,
    declared: &Bound<'_, PyAny>,
) -> PyResult<Vec<(String, Vec<Vec<String>>)>> {
    let mut keys: Vec<(String, Vec<Vec<String>>)> = Vec::new();
    for relation in body.getattr("dependency_relations")?.try_iter()? {
        let (sentinel, name): (String, Bound<'_, PyAny>) = relation?.extract()?;
        let found: Bound<'_, PyAny> = declared.call_method1("get", (name,))?;
        if found.is_truthy()? {
            keys.push((sentinel, found.extract()?));
        }
    }
    Ok(keys)
}

fn lint_body(
    body: &Bound<'_, PyAny>,
    index_by_path: &Bound<'_, PyDict>,
    declared: &Bound<'_, PyAny>,
) -> PyResult<LintSqlBody> {
    let file: usize = index_by_path
        .as_any()
        .get_item(body.getattr("file_path")?)?
        .extract()?;
    Ok(LintSqlBody {
        file,
        body_start: body.getattr("body_start")?.extract()?,
        lint_text: body.getattr("lint_text")?.extract()?,
        passes: spans(&body.getattr("passes")?)?,
        external_identifiers: body.getattr("external_identifiers")?.extract()?,
        dependency_identifiers: body.getattr("dependency_identifiers")?.extract()?,
        externally_referenced_ctes: body.getattr("externally_referenced_ctes")?.extract()?,
        allows_ceremonial_select: body.getattr("allows_ceremonial_select")?.extract()?,
        allows_dynamic_output_star: body.getattr("allows_dynamic_output_star")?.extract()?,
        allows_empty_fixture_star: body.getattr("allows_empty_fixture_star")?.extract()?,
        relation_keys: relation_keys(body, declared)?,
    })
}

fn options(config: &Bound<'_, PyAny>) -> PyResult<LintSqlOptions> {
    Ok(LintSqlOptions {
        dialect: config.getattr("dialect")?.extract()?,
        enabled_rules: config.getattr("enabled_native_rules")?.extract()?,
        ignored_rules: config.getattr("ignored_native_rules")?.extract()?,
        max_literal_length: config.getattr("max_literal_length")?.extract()?,
        max_ranking_order_by: config.getattr("max_ranking_order_by")?.extract()?,
    })
}

/// The lint model classes native SQL diagnostics are built as.
struct ViolationClasses<'py> {
    violation: Bound<'py, PyAny>,
    edit: Bound<'py, PyAny>,
    severity: Bound<'py, PyAny>,
}

impl<'py> ViolationClasses<'py> {
    fn new(py: Python<'py>) -> PyResult<Self> {
        Ok(Self {
            violation: imported(py, LINT_MODELS_MODULE, "LintViolation")?,
            edit: imported(py, LINT_MODELS_MODULE, "LintEdit")?,
            severity: imported(py, LINT_TYPES_MODULE, "LintSeverity")?,
        })
    }

    fn violation(
        &self,
        file_path: &Bound<'py, PyAny>,
        diagnostic: AuthoredDiagnostic,
    ) -> PyResult<Bound<'py, PyAny>> {
        let py: Python<'py> = file_path.py();
        let none = || py.None().into_bound(py);
        let code: Bound<'py, PyAny> = PyString::new(py, &diagnostic.code).into_any();
        let fix: Bound<'py, PyAny> = match diagnostic.fix {
            Some(edit) => call_with(
                &self.edit,
                &[
                    ("file_path", file_path.clone()),
                    ("code", code.clone()),
                    ("start", edit.start.into_pyobject(py)?.into_any()),
                    ("end", edit.end.into_pyobject(py)?.into_any()),
                    (
                        "replacement",
                        PyString::new(py, &edit.replacement).into_any(),
                    ),
                ],
            )?,
            None => none(),
        };
        let (end_line, end_column) = match diagnostic.end {
            Some((line, column)) => (
                line.into_pyobject(py)?.into_any(),
                column.into_pyobject(py)?.into_any(),
            ),
            None => (none(), none()),
        };
        let severity: &str = if diagnostic.fault { "FAULT" } else { "WARNING" };
        call_with(
            &self.violation,
            &[
                ("file_path", file_path.clone()),
                ("line", diagnostic.line.into_pyobject(py)?.into_any()),
                ("column", diagnostic.column.into_pyobject(py)?.into_any()),
                ("code", code),
                ("message", PyString::new(py, &diagnostic.message).into_any()),
                ("severity", self.severity.getattr(severity)?),
                ("engine", PyString::new(py, NATIVE_ENGINE).into_any()),
                ("end_line", end_line),
                ("end_column", end_column),
                (
                    "remediation",
                    PyString::new(py, &diagnostic.remediation).into_any(),
                ),
                ("fix", fix),
                (
                    "fix_unavailable_reason",
                    diagnostic
                        .fix_unavailable_reason
                        .map_or_else(none, |reason| PyString::new(py, &reason).into_any()),
                ),
            ],
        )
    }
}

/// Lint expanded bodies natively and map every diagnostic onto authored source.
#[pyfunction]
fn lint_native_sql_bodies<'py>(
    py: Python<'py>,
    bodies: Vec<Bound<'py, PyAny>>,
    contents_by_path: Bound<'py, PyDict>,
    config: Bound<'py, PyAny>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let index_by_path: Bound<'py, PyDict> = PyDict::new(py);
    let mut paths: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut texts: Vec<String> = Vec::new();
    for (path, text) in contents_by_path.iter() {
        index_by_path.set_item(&path, paths.len())?;
        paths.push(path);
        texts.push(text.extract()?);
    }
    let declared: Bound<'py, PyAny> = config.getattr("relation_keys")?;
    let inputs: Vec<LintSqlBody> = bodies
        .iter()
        .map(|body| lint_body(body, &index_by_path, &declared))
        .collect::<PyResult<_>>()?;
    let options: LintSqlOptions = options(&config)?;
    let diagnostics: Vec<AuthoredDiagnostic> = py
        .compiler_detach(|| {
            let files: Vec<&str> = texts.iter().map(String::as_str).collect();
            Ok(lint_sql_bodies(&inputs, &files, &options))
        })
        .map_err(value_error)?;
    let classes: ViolationClasses<'py> = ViolationClasses::new(py)?;
    diagnostics
        .into_iter()
        .map(|diagnostic| classes.violation(&paths[diagnostic.file], diagnostic))
        .collect()
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(lint_native_sql_bodies, module)?)
}
