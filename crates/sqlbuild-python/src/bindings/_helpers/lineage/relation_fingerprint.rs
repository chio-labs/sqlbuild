//! The relation lineage cache key for the preview compiler engine.

use std::path::PathBuf;

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::lineage::main::relation_fingerprint::relation_fingerprint;
use sqlbuild_analysis::lineage::models::InterruptedListingPolicy;

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::types::CompilerDetach;

/// `(status, digest)` of the authored files; the flag is true where `rglob` raises mid-listing.
#[pyfunction]
fn relation_lineage_fingerprint(
    py: Python<'_>,
    project_dir: PathBuf,
    prefix: Vec<u8>,
    interrupted_listing_uncacheable: bool,
) -> PyResult<(&'static str, Option<String>)> {
    let policy = if interrupted_listing_uncacheable {
        InterruptedListingPolicy::Uncacheable
    } else {
        InterruptedListingPolicy::Skip
    };
    py.compiler_detach(|| Ok(relation_fingerprint(&project_dir, &prefix, policy).into_parts()))
        .map_err(compiler_error)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(relation_lineage_fingerprint, module)?)?;
    Ok(())
}
