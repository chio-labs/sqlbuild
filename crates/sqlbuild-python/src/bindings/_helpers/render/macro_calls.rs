//! Macro call-site scanning and splicing for the Python macro bridge, with the GIL released.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::panics::main::native_failure::native_failure;
use sqlbuild_core::text::main::python_text::python_text;
use sqlbuild_render::macro_calls::main::scan_macro_call_sites::scan_macro_call_sites as scan_sites;
use sqlbuild_render::macro_calls::main::splice_macro_calls::splice_macro_calls as splice_calls;
use sqlbuild_render::macro_calls::models::{MacroCallScan, MacroScanFailure};

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::_helpers::render::macro_call_memo::MacroCallMemo;
use crate::bindings::_helpers::render::macro_call_rows::{SiteRow, SpanRow, site_row, span_row};
use crate::bindings::types::CompilerDetach;

/// `(call start or None, message)` of the error Python's scan raises.
type FailureRow = (Option<usize>, &'static str);

/// Every complete top-level macro call site of `sql`, and where Python's scan raises, if it does.
#[pyfunction]
pub(crate) fn scan_macro_call_sites(
    py: Python<'_>,
    sql: &str,
    python_version: (u8, u8),
    unicode_version: &str,
) -> PyResult<(Vec<SiteRow>, Option<FailureRow>)> {
    let python = python_text(python_version, unicode_version).ok_or_else(|| {
        compiler_error(native_failure(
            MACRO_SCAN_CONTEXT,
            "the macro bridge runs on a Python whose text tables are not compiled in",
        ))
    })?;
    let MacroCallScan { sites, failure } = py
        .compiler_detach(|| Ok(scan_sites(python, sql)))
        .map_err(compiler_error)?;
    Ok((
        sites.into_iter().map(site_row).collect(),
        failure.map(|MacroScanFailure { call_start, error }| (call_start, error.message())),
    ))
}

const MACRO_SCAN_CONTEXT: &str = "native macro call scan";

/// Splice rendered macro outputs over their call sites, returning the SQL and substitution spans.
#[pyfunction]
pub(crate) fn splice_macro_calls(
    py: Python<'_>,
    sql: &str,
    sites: Vec<(usize, usize)>,
    outputs: Vec<String>,
) -> PyResult<(String, Vec<SpanRow>)> {
    let spliced = py
        .compiler_detach(|| Ok(splice_calls(sql, &sites, &outputs)))
        .map_err(compiler_error)?;
    let (rendered, spans) =
        spliced.ok_or_else(|| PyValueError::new_err("macro call sites do not fit the SQL"))?;
    Ok((rendered, spans.into_iter().map(span_row).collect()))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(scan_macro_call_sites, module)?)?;
    module.add_function(wrap_pyfunction!(splice_macro_calls, module)?)?;
    module.add_class::<MacroCallMemo>()?;
    Ok(())
}
