//! A hand-built model's binding diagnostics at their authored locations.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::binding_locations::main::locate_binding_diagnostics::locate_binding_diagnostics;
use sqlbuild_analysis::binding_locations::models::{BindingSource, LocatedDiagnostic};
use sqlbuild_analysis::semantic_validation::types::{DiagnosticRow, Expansion};

/// `(code, message, severity, line, column, (line, column, end line, end column))`.
type LocatedRow = (
    String,
    String,
    String,
    Option<usize>,
    Option<usize>,
    Option<(usize, usize, Option<usize>, Option<usize>)>,
);

/// Each reported diagnostic of `rows` through `(authored, query, cleaned)` and the expansion.
#[pyfunction]
fn locate_model_binding_diagnostics(
    rows: Vec<DiagnosticRow>,
    texts: (String, String, String),
    expansion: Option<(String, Vec<Vec<Expansion>>)>,
) -> PyResult<Vec<LocatedRow>> {
    let (authored, query, cleaned) = texts;
    let source: BindingSource<'_> = BindingSource {
        authored: &authored,
        query: &query,
        cleaned: &cleaned,
        expansion: expansion
            .as_ref()
            .map(|(expanded, passes)| (expanded.as_str(), passes.as_slice())),
    };
    let located: Vec<LocatedDiagnostic> =
        locate_binding_diagnostics(&rows, &source).map_err(PyValueError::new_err)?;
    Ok(located.into_iter().map(located_row).collect())
}

fn located_row(item: LocatedDiagnostic) -> LocatedRow {
    let span = item
        .location
        .map(|span| (span.line, span.column, span.end_line, span.end_column));
    (
        item.code,
        item.message,
        item.severity,
        item.line,
        item.column,
        span,
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(locate_model_binding_diagnostics, module)?)?;
    Ok(())
}
