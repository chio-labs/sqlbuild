//! Rules results rendered for the CLI, and SQBRSQL044 help naming files that repeat a literal.

use pyo3::exceptions::PyOSError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use std::path::PathBuf;

use sqlbuild_core::text::main::python_splitlines::python_splitlines;
use sqlbuild_rules::rule_results::main::duplicate_literal_hints::duplicate_literal_hints;
use sqlbuild_rules::rule_results::main::format_result::format_result;
use sqlbuild_rules::rule_results::main::format_rules_progress::format_rules_progress;
use sqlbuild_rules::rule_results::main::format_skipped_rules::format_skipped_rules;
use sqlbuild_rules::rule_results::models::{ResultCounts, RuleFinding};

use crate::bindings::_helpers::compile_driver::python_calls::call_with;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::fields::{field, path_posix, replaced};

const UTF8: &str = "utf-8";

pub(crate) fn rule_finding(finding: &Bound<'_, PyAny>) -> PyResult<RuleFinding> {
    Ok(RuleFinding {
        code: field(finding, "code")?.extract()?,
        path: path_posix(&field(finding, "path")?)?,
        line: field(finding, "line")?.extract()?,
        column: field(finding, "column")?.extract()?,
        message: field(finding, "message")?.extract()?,
        remediation: field(finding, "remediation")?.extract()?,
        unevaluated: field(finding, "unevaluated")?.is_truthy()?,
        affected_rules: field(finding, "affected_rules")?.extract()?,
        fixable: field(finding, "fixable")?.is_truthy()?,
    })
}

fn rule_findings(findings: &Bound<'_, PyAny>) -> PyResult<Vec<RuleFinding>> {
    findings
        .try_iter()?
        .map(|finding| rule_finding(&finding?))
        .collect()
}

/// One rules result for the requested CLI surface.
#[pyfunction]
#[pyo3(signature = (*, result, json_output))]
pub(crate) fn format_rules_result(
    result: &Bound<'_, PyAny>,
    json_output: bool,
) -> PyResult<String> {
    let counts = ResultCounts {
        evaluated_models: field(result, "evaluated_models")?.extract()?,
        unevaluated_resources: field(result, "unevaluated_resources")?.extract()?,
        cache_hits: field(result, "cache_hits")?.extract()?,
        cache_misses: field(result, "cache_misses")?.extract()?,
    };
    Ok(format_result(
        &rule_findings(&field(result, "findings")?)?,
        counts,
        json_output,
    ))
}

/// The rules phase completion line for one `RulesRunResult`, optionally noting skipped rules.
pub(crate) fn rules_progress(
    elapsed_seconds: f64,
    result: &Bound<'_, PyAny>,
    note_skipped_rules: bool,
) -> PyResult<String> {
    let skipped: Option<Vec<String>> = if note_skipped_rules {
        Some(field(result, "skipped_type_proof_rules")?.extract()?)
    } else {
        None
    };
    Ok(format_rules_progress(
        elapsed_seconds,
        (
            field(result, "built_in_ms")?.extract()?,
            field(result, "custom_ms")?.extract()?,
        ),
        skipped.as_deref(),
    ))
}

/// Describe type-proof rules skipped because SQL analysis is disabled, if any.
#[pyfunction]
#[pyo3(signature = (*, codes))]
pub(crate) fn format_skipped_type_proof_rules(codes: Vec<String>) -> Option<String> {
    format_skipped_rules(&codes)
}

/// The authored lines of one finding's file; an unreadable file has none.
fn file_lines(project_dir: &Bound<'_, PyAny>, path: &str) -> PyResult<Vec<String>> {
    let py = project_dir.py();
    let root: PathBuf = project_dir.extract()?;
    let Ok(bytes) = std::fs::read(root.join(path)) else {
        return Ok(Vec::new());
    };
    if let Ok(text) = std::str::from_utf8(&bytes) {
        return Ok(python_splitlines(text)
            .into_iter()
            .map(str::to_owned)
            .collect());
    }
    let file: Bound<'_, PyAny> = project_dir.div(path)?;
    let read: PyResult<Bound<'_, PyAny>> = call_with(
        &native_field(&file, "read_text")?,
        &[("encoding", PyString::new(py, UTF8).into_any())],
    );
    match read {
        Ok(text) => text.call_method0("splitlines")?.extract(),
        Err(error) if error.is_instance_of::<PyOSError>(py) => Ok(Vec::new()),
        Err(error) => Err(error),
    }
}

/// Prefix SQBRSQL044 help with the other files that repeat the identical literal.
#[pyfunction]
#[pyo3(signature = (*, findings, project_dir))]
fn with_duplicate_literal_hints<'py>(
    findings: &Bound<'py, PyAny>,
    project_dir: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py = findings.py();
    let originals: Vec<Bound<'py, PyAny>> = findings.try_iter()?.collect::<PyResult<_>>()?;
    let rows: Vec<RuleFinding> = originals
        .iter()
        .map(rule_finding)
        .collect::<PyResult<_>>()?;
    let hinted: Vec<Option<String>> =
        duplicate_literal_hints::<PyErr>(&rows, |path| file_lines(project_dir, path))?;
    let mut output: Vec<Bound<'py, PyAny>> = Vec::with_capacity(originals.len());
    for (finding, remediation) in originals.into_iter().zip(hinted) {
        output.push(match remediation {
            Some(remediation) => replaced(
                &finding,
                &[("remediation", PyString::new(py, &remediation).into_any())],
            )?,
            None => finding,
        });
    }
    PyTuple::new(py, output)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(format_rules_result, module)?)?;
    module.add_function(wrap_pyfunction!(format_skipped_type_proof_rules, module)?)?;
    module.add_function(wrap_pyfunction!(with_duplicate_literal_hints, module)?)?;
    Ok(())
}
