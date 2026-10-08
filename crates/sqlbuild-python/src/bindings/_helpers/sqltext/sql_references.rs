//! Logical SQL references extracted natively under one adapter's lexical rules.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyclass, pymethods};
use sqlbuild_sqltext::sql_references::main::extract_sql_references::extract_sql_references;
use sqlbuild_sqltext::sql_references::models::{
    InvalidReferenceCall, ReferenceExtraction, SqlReference,
};
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::bindings::_helpers::boundary::panics::compiler_guard;
use crate::bindings::_helpers::sqltext::lexical_syntax::LexicalSyntaxInput;

/// `(kind, name, package, call_argument_count)` for one reference.
type ReferenceRow = (&'static str, String, Option<String>, Option<usize>);
/// `(kind, call, start, message, help, corrected_call)` for one rejected call.
type InvalidCallRow = (&'static str, String, usize, String, String, String);
/// The references and rejected calls, or Python's error message; `None` defers to Python.
type ExtractionRow = Option<(
    Option<(Vec<ReferenceRow>, Vec<InvalidCallRow>)>,
    Option<String>,
)>;

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

    /// Return `((references, rejected calls), None)`, `(None, message)`, or `None` to defer.
    fn extract(&self, sql: &str) -> PyResult<ExtractionRow> {
        compiler_guard(|| {
            Ok(match extract_sql_references(sql, &self.syntax) {
                ReferenceExtraction::Extracted(scan) => Some((
                    Some((
                        scan.references.into_iter().map(reference_row).collect(),
                        scan.invalid_calls
                            .into_iter()
                            .map(invalid_call_row)
                            .collect(),
                    )),
                    None,
                )),
                ReferenceExtraction::Failed(message) => Some((None, Some(message))),
                ReferenceExtraction::Deferred => None,
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

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<SqlReferenceScanner>()?;
    Ok(())
}
