//! Rules results rendered for the CLI, and SQBRSQL044 help naming files that repeat a literal.

use pyo3::exceptions::PyOSError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_rules::rule_results::main::duplicate_literal_hints::duplicate_literal_hints;
use sqlbuild_rules::rule_results::main::format_result::format_result;
use sqlbuild_rules::rule_results::models::{ResultCounts, RuleFinding};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};

const DATACLASSES_MODULE: &str = "dataclasses";
const UTF8: &str = "utf-8";

fn rule_finding(finding: &Bound<'_, PyAny>) -> PyResult<RuleFinding> {
    Ok(RuleFinding {
        code: finding.getattr("code")?.extract()?,
        path: finding
            .getattr("path")?
            .call_method0("as_posix")?
            .extract()?,
        line: finding.getattr("line")?.extract()?,
        column: finding.getattr("column")?.extract()?,
        message: finding.getattr("message")?.extract()?,
        remediation: finding.getattr("remediation")?.extract()?,
        unevaluated: finding.getattr("unevaluated")?.is_truthy()?,
        affected_rules: finding.getattr("affected_rules")?.extract()?,
        fixable: finding.getattr("fixable")?.is_truthy()?,
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
fn format_rules_result(result: &Bound<'_, PyAny>, json_output: bool) -> PyResult<String> {
    let counts = ResultCounts {
        evaluated_models: result.getattr("evaluated_models")?.extract()?,
        unevaluated_resources: result.getattr("unevaluated_resources")?.extract()?,
        cache_hits: result.getattr("cache_hits")?.extract()?,
        cache_misses: result.getattr("cache_misses")?.extract()?,
    };
    Ok(format_result(
        &rule_findings(&result.getattr("findings")?)?,
        counts,
        json_output,
    ))
}

/// The authored lines of one finding's file; an unreadable file has none.
fn file_lines(project_dir: &Bound<'_, PyAny>, path: &str) -> PyResult<Vec<String>> {
    let py = project_dir.py();
    let file: Bound<'_, PyAny> = project_dir.div(path)?;
    let read: PyResult<Bound<'_, PyAny>> = call_with(
        &file.getattr("read_text")?,
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
    let replace: Bound<'py, PyAny> = imported(py, DATACLASSES_MODULE, "replace")?;
    let mut output: Vec<Bound<'py, PyAny>> = Vec::with_capacity(originals.len());
    for (finding, remediation) in originals.into_iter().zip(hinted) {
        output.push(match remediation {
            Some(remediation) => {
                let keywords: Bound<'py, PyDict> = PyDict::new(py);
                keywords.set_item("remediation", remediation)?;
                replace.call((finding,), Some(&keywords))?
            }
            None => finding,
        });
    }
    PyTuple::new(py, output)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(format_rules_result, module)?)?;
    module.add_function(wrap_pyfunction!(with_duplicate_literal_hints, module)?)?;
    Ok(())
}
