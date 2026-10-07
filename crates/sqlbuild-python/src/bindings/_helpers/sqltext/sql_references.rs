//! Logical SQL references extracted natively under one adapter's lexical rules.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyclass, pymethods};
use sqlbuild_sqltext::sql_references::main::extract_sql_references::extract_sql_references;
use sqlbuild_sqltext::sql_references::models::{ReferenceExtraction, SqlReference};
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::bindings::_helpers::boundary::panics::compiler_guard;
use crate::bindings::_helpers::sqltext::lexical_syntax::LexicalSyntaxInput;

/// `(kind, name, package, call_argument_count)` for one reference.
type ReferenceRow = (&'static str, String, Option<String>, Option<usize>);
/// The references, or Python's error message; `None` defers the text to Python.
type ExtractionRow = Option<(Option<Vec<ReferenceRow>>, Option<String>)>;

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

    /// Return `(references, None)`, `(None, message)` when Python raises, or `None` to defer.
    fn extract(&self, sql: &str) -> PyResult<ExtractionRow> {
        compiler_guard(|| {
            Ok(match extract_sql_references(sql, &self.syntax) {
                ReferenceExtraction::Extracted(references) => Some((
                    Some(references.into_iter().map(reference_row).collect()),
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

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<SqlReferenceScanner>()?;
    Ok(())
}
