//! Call-site scanning and splicing for the Python macro bridge, with the GIL released.

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::{PyResult, Python};
use pyo3::pyfunction;
use sqlbuild_core::text::main::python_text::python_text;
use sqlbuild_render::macro_calls::main::scan_macro_call_sites::scan_macro_call_sites as scan_sites;
use sqlbuild_render::macro_calls::main::splice_macro_calls::splice_macro_calls as splice_calls;
use sqlbuild_render::macro_calls::models::ScanDeferral;

use crate::bindings::types::CompilerDetach;
use crate::macro_bridge::_helpers::rows::{site_row, span_row};
use crate::macro_bridge::types::{SiteRow, SpanRow};

fn compiler_error(message: String) -> pyo3::PyErr {
    PyRuntimeError::new_err(message)
}

/// Every top-level macro call site of `sql`, or `None` when Python must expand the string.
#[pyfunction]
pub(crate) fn scan_macro_call_sites(
    py: Python<'_>,
    sql: &str,
    python_version: (u8, u8),
    unicode_version: &str,
) -> PyResult<Option<Vec<SiteRow>>> {
    let Some(python) = python_text(python_version, unicode_version) else {
        return Ok(None);
    };
    let scanned = py
        .compiler_detach(|| Ok(scan_sites(python, sql)))
        .map_err(compiler_error)?;
    match scanned {
        Ok(sites) => Ok(Some(sites.into_iter().map(site_row).collect())),
        Err(ScanDeferral) => Ok(None),
    }
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
