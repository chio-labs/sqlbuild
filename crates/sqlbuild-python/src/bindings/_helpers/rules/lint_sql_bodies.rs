//! Native SQL lint of prepared lint bodies, as Python lint violations.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_rules::lint_text::main::lint_sql_bodies::lint_sql_bodies;
use sqlbuild_rules::lint_text::models::{
    AuthoredDiagnostic, ExpansionSpan, LintSqlBody, LintSqlOptions,
};

use crate::bindings::_helpers::boundary::panics::value_error;
use crate::bindings::_helpers::rules::lint_pipeline::{LintViolationRow, ViolationClasses};
use crate::bindings::types::CompilerDetach;

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
        .map(|diagnostic| {
            let row: LintViolationRow = LintViolationRow::diagnostic(diagnostic);
            classes.violation(&paths[row.file], &row)
        })
        .collect()
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(lint_native_sql_bodies, module)?)
}
