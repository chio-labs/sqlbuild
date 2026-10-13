//! Logical SQL references extracted natively under one adapter's lexical rules.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use pyo3::{IntoPyObject, IntoPyObjectExt, pyclass, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_sqltext::sql_references::main::extract_sql_references::extract_sql_references;
use sqlbuild_sqltext::sql_references::models::{
    InvalidReferenceCall, ReferenceExtraction, SqlReference,
};
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::bindings::_helpers::boundary::panics::compiler_guard;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::sqltext::lexical_syntax::LexicalSyntaxInput;

const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const COMPILE_TYPES_MODULE: &str = "sqlbuild.compiler.compile.types";
const COMPILE_ERRORS_MODULE: &str = "sqlbuild.compiler.compile.exceptions";
const REFERENCE_TYPES_MODULE: &str = "sqlbuild.compiler.references.types";
const COLLECTOR_MODULE: &str = "sqlbuild.compiler.compile._helpers.diagnostics.collector";
const REFERENCE_CALL_SYNTAX_CODE: &str = "P012";

/// `(kind, name, package, call_argument_count)` for one reference.
type ReferenceRow = (&'static str, String, Option<String>, Option<usize>);
/// `(kind, call, start, message, help, corrected_call)` for one rejected call.
type InvalidCallRow = (&'static str, String, usize, String, String, String);
/// Python references and rejected calls of one scan.
type ScannedObjects<'py> = (Vec<Bound<'py, PyAny>>, Vec<Bound<'py, PyAny>>);
/// The references and rejected calls, or the scan error and its start.
type ExtractionRow = (
    Option<(Vec<ReferenceRow>, Vec<InvalidCallRow>)>,
    Option<(String, usize)>,
);

/// Extracts references under one adapter's lexical rules, read once per syntax.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct SqlReferenceScanner {
    syntax: LexicalSyntax,
}

#[pymethods]
impl SqlReferenceScanner {
    #[new]
    fn new(syntax: LexicalSyntaxInput) -> Self {
        Self {
            syntax: syntax.into(),
        }
    }

    /// Return `((references, rejected calls), None)` or `(None, (message, start))`.
    fn extract(&self, sql: &str) -> PyResult<ExtractionRow> {
        compiler_guard(|| {
            Ok(match extract_sql_references(sql, &self.syntax) {
                ReferenceExtraction::Extracted(scan) => (
                    Some((
                        scan.references.into_iter().map(reference_row).collect(),
                        scan.invalid_calls
                            .into_iter()
                            .map(invalid_call_row)
                            .collect(),
                    )),
                    None,
                ),
                ReferenceExtraction::Failed(failure) => {
                    (None, Some((failure.message, failure.start)))
                }
            })
        })
    }
}

fn reference_row(reference: SqlReference) -> ReferenceRow {
    (
        reference.kind,
        reference.name,
        reference.package,
        reference.call_argument_count,
    )
}

fn invalid_call_row(call: InvalidReferenceCall) -> InvalidCallRow {
    (
        call.kind,
        call.call,
        call.start,
        call.message,
        call.help,
        call.corrected_call,
    )
}

fn text<'py>(py: Python<'py>, value: impl IntoPyObject<'py>) -> PyResult<Bound<'py, PyAny>> {
    value.into_bound_py_any(py)
}

/// The references and rejected calls `sql` holds as Python objects; a scan error raises.
fn scanned<'py>(
    py: Python<'py>,
    sql: &str,
    syntax: &Bound<'py, PyAny>,
) -> PyResult<ScannedObjects<'py>> {
    let input: LexicalSyntaxInput = syntax.getattr("native_mapping")?.extract()?;
    let syntax: LexicalSyntax = input.into();
    let scan = match compiler_guard(|| Ok(extract_sql_references(sql, &syntax)))? {
        ReferenceExtraction::Extracted(scan) => scan,
        ReferenceExtraction::Failed(failure) => {
            let error: Bound<'py, PyAny> =
                imported(py, COMPILE_ERRORS_MODULE, "CompileInputError")?
                    .call1((failure.message,))?;
            return Err(PyErr::from_value(error));
        }
    };
    let kind_type: Bound<'py, PyAny> = imported(py, REFERENCE_TYPES_MODULE, "SqlReferenceKind")?;
    let reference_type: Bound<'py, PyAny> =
        imported(py, COMPILE_MODELS_MODULE, "CompileSqlReference")?;
    let invalid_type: Bound<'py, PyAny> =
        imported(py, COMPILE_MODELS_MODULE, "InvalidSqlReferenceCall")?;
    let references: Vec<Bound<'py, PyAny>> = scan
        .references
        .into_iter()
        .map(|reference| {
            call_with(
                &reference_type,
                &[
                    ("ref_kind", kind_type.call1((reference.kind,))?),
                    ("ref_name", text(py, reference.name)?),
                    ("ref_package", text(py, reference.package)?),
                    (
                        "call_argument_count",
                        text(py, reference.call_argument_count)?,
                    ),
                ],
            )
        })
        .collect::<PyResult<_>>()?;
    let invalid_calls: Vec<Bound<'py, PyAny>> = scan
        .invalid_calls
        .into_iter()
        .map(|call| {
            call_with(
                &invalid_type,
                &[
                    ("ref_kind", kind_type.call1((call.kind,))?),
                    ("call", text(py, call.call)?),
                    ("start", text(py, call.start)?),
                    ("message", text(py, call.message)?),
                    ("help", text(py, call.help)?),
                    ("corrected_call", text(py, call.corrected_call)?),
                ],
            )
        })
        .collect::<PyResult<_>>()?;
    Ok((references, invalid_calls))
}

/// Valid references and rejected calls; a scan error raises unlocated.
#[pyfunction]
#[pyo3(signature = (*, sql, syntax))]
fn scan_sql_reference_calls<'py>(
    sql: &str,
    syntax: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = syntax.py();
    let (references, invalid_calls) = scanned(py, sql, syntax)?;
    call_with(
        &imported(py, COMPILE_MODELS_MODULE, "SqlReferenceScan")?,
        &[
            ("references", PyTuple::new(py, references)?.into_any()),
            ("invalid_calls", PyTuple::new(py, invalid_calls)?.into_any()),
        ],
    )
}

/// Logical SQL refs outside comments and quotes, reporting rejected calls as P012.
#[pyfunction(name = "extract_sql_references")]
#[pyo3(signature = (*, sql, syntax))]
fn extract_references<'py>(sql: &str, syntax: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = syntax.py();
    let (references, invalid_calls) = scanned(py, sql, syntax)?;
    let report: Bound<'py, PyAny> = imported(py, COLLECTOR_MODULE, "report_compile_diagnostic")?;
    let diagnostic_type: Bound<'py, PyAny> =
        imported(py, COMPILE_MODELS_MODULE, "CompilerDiagnostic")?;
    let types = py.import(COMPILE_TYPES_MODULE)?;
    for call in invalid_calls {
        let diagnostic: Bound<'py, PyAny> = call_with(
            &diagnostic_type,
            &[
                (
                    "phase",
                    types.getattr("DiagnosticPhase")?.getattr("COMPILE")?,
                ),
                (
                    "severity",
                    types.getattr("DiagnosticSeverity")?.getattr("ERROR")?,
                ),
                ("code", text(py, REFERENCE_CALL_SYNTAX_CODE)?),
                ("message", call.getattr("message")?),
                ("help", call.getattr("help")?),
            ],
        )?;
        let keywords: Bound<'py, PyDict> = PyDict::new(py);
        keywords.set_item(
            "key",
            (REFERENCE_CALL_SYNTAX_CODE, "", call.getattr("call")?),
        )?;
        keywords.set_item("diagnostic", diagnostic)?;
        report.call((), Some(&keywords))?;
    }
    PyTuple::new(py, references)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<SqlReferenceScanner>()?;
    module.add_function(wrap_pyfunction!(scan_sql_reference_calls, module)?)?;
    module.add_function(wrap_pyfunction!(extract_references, module)?)?;
    Ok(())
}
