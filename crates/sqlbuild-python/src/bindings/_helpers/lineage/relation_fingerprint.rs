//! The relation lineage cache key for the preview compiler engine.

use std::path::PathBuf;

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::lineage::main::relation_fingerprint::relation_fingerprint;

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::types::CompilerDetach;

/// `(status, digest)` for `project_dir`'s authored files after Python's encoded `prefix`.
#[pyfunction]
fn relation_lineage_fingerprint(
    py: Python<'_>,
    project_dir: PathBuf,
    prefix: Vec<u8>,
) -> PyResult<(&'static str, Option<String>)> {
    py.compiler_detach(|| Ok(relation_fingerprint(&project_dir, &prefix).into_parts()))
        .map_err(compiler_error)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(relation_lineage_fingerprint, module)?)?;
    Ok(())
}
