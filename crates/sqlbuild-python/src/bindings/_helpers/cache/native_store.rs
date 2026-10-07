//! Digests and project fingerprints of the shared native store, with the GIL released.

use pyo3::exceptions::{PyOSError, PyRuntimeError};
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_cache::digest::main::content_digest::content_digest as digest;
use sqlbuild_cache::digest::main::fingerprint_project_files::fingerprint_project_files as fingerprint;
use sqlbuild_cache::digest::main::hex_digest::hex_digest;
use sqlbuild_cache::digest::types::ContentDigest;
use std::collections::HashSet;
use std::path::PathBuf;

use crate::bindings::types::CompilerDetach;

/// Hexadecimal digest of length-prefixed UTF-8 `parts`, the digest every native cache key uses.
#[pyfunction]
pub(crate) fn content_digest(parts: Vec<String>) -> String {
    hex_digest(&digest(&parts))
}

/// Digest of every project file outside skipped folders and `excluded_files`, else `OSError`.
#[pyfunction]
pub(crate) fn fingerprint_project_files(
    py: Python<'_>,
    root: PathBuf,
    excluded_files: Vec<String>,
) -> PyResult<String> {
    let excluded: HashSet<String> = excluded_files.into_iter().collect();
    let fingerprinted: ContentDigest = py
        .compiler_detach(|| Ok(fingerprint(&root, &excluded)))
        .map_err(PyRuntimeError::new_err)?
        .map_err(|error| PyOSError::new_err(error.to_string()))?;
    Ok(hex_digest(&fingerprinted))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(content_digest, module)?)?;
    module.add_function(wrap_pyfunction!(fingerprint_project_files, module)?)?;
    Ok(())
}
