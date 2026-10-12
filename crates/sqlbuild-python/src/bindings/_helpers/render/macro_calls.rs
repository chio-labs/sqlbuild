//! Macro call-site scanning and splicing for the Python macro bridge, with the GIL released.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_render::macro_calls::main::macro_call_names::macro_call_names as scan_names;
use sqlbuild_render::macro_calls::main::scan_macro_call_sites::scan_macro_call_sites as scan_sites;
use sqlbuild_render::macro_calls::main::splice_macro_calls::splice_macro_calls as splice_calls;
use sqlbuild_render::macro_calls::models::{MacroCallScan, MacroScanFailure};

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::_helpers::render::macro_call_memo::MacroCallMemo;
use crate::bindings::_helpers::render::macro_call_rows::{SiteRow, SpanRow, site_row, span_row};
use crate::bindings::types::CompilerDetach;

/// `(call start or None, call name or None, message)` of the error Python's scan raises.
type FailureRow = (Option<usize>, Option<String>, &'static str);

/// Every complete top-level macro call site of `sql`, and where Python's scan raises, if it does.
#[pyfunction]
pub(crate) fn scan_macro_call_sites(
    py: Python<'_>,
    sql: &str,
) -> PyResult<(Vec<SiteRow>, Option<FailureRow>)> {
    let MacroCallScan { sites, failure } = py
        .compiler_detach(|| Ok(scan_sites(sql)))
        .map_err(compiler_error)?;
    Ok((
        sites.into_iter().map(site_row).collect(),
        failure.map(
            |MacroScanFailure {
                 call_start,
                 call_name,
                 error,
             }| (call_start, call_name, error.message()),
        ),
    ))
}

/// Python's `find_macro_call_names` names, or the `CompileInputError` message of its scan.
#[pyfunction]
pub(crate) fn macro_call_names(
    py: Python<'_>,
    sql: &str,
    nested: bool,
) -> PyResult<(Option<Vec<String>>, Option<&'static str>)> {
    let names = py
        .compiler_detach(|| Ok(scan_names(sql, nested)))
        .map_err(compiler_error)?;
    Ok(match names {
        Ok(names) => (Some(names), None),
        Err(error) => (None, Some(error.message())),
    })
}

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
    module.add_function(wrap_pyfunction!(macro_call_names, module)?)?;
    module.add_function(wrap_pyfunction!(splice_macro_calls, module)?)?;
    module.add_class::<MacroCallMemo>()?;
    Ok(())
}
