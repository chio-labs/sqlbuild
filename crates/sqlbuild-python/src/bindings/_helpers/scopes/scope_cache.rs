//! The persistent scope index cache: fingerprint, verified read and atomic write.

use std::path::PathBuf;

use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::{Bound, Py, PyAny, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_scopes::scope_cache::main::encode_scope_cache::encode_scope_cache;
use sqlbuild_scopes::scope_cache::main::read_scope_cache::read_scope_cache;
use sqlbuild_scopes::scope_cache::main::scope_fingerprint::scope_fingerprint;
use sqlbuild_scopes::scope_cache::main::write_scope_cache::write_scope_cache;
use sqlbuild_scopes::scope_cache::models::{CachedIndex, Fingerprint, FingerprintInputs};

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::_helpers::scopes::scope_objects::{
    ScopeClasses, index_object, read_completeness, read_index,
};
use crate::bindings::types::CompilerDetach;

/// Config files, candidate roots, declaration folders, named declaration folders, version.
type FingerprintRow = (Vec<String>, Vec<String>, Vec<String>, Vec<String>, String);

/// The scope index fingerprint of `project_dir`, `None` when it cannot be read.
#[pyfunction]
fn scope_index_fingerprint(
    py: Python<'_>,
    project_dir: PathBuf,
    inputs: FingerprintRow,
) -> PyResult<Option<String>> {
    let (config_files, roots, declaration_directories, named_declaration_directories, version) =
        inputs;
    let inputs: FingerprintInputs = FingerprintInputs {
        config_files,
        roots,
        declaration_directories,
        named_declaration_directories,
        sqlbuild_version: version,
    };
    let fingerprint: Fingerprint = py
        .compiler_detach(|| Ok(scope_fingerprint(&project_dir, &inputs)))
        .map_err(compiler_error)?;
    match fingerprint {
        Fingerprint::Hash(hash) => Ok(Some(hash)),
        Fingerprint::Unavailable => Ok(None),
        Fingerprint::Unserializable => Err(PyTypeError::new_err(
            "a scope-relevant config value is not JSON serializable",
        )),
    }
}

/// The verified cached `ScopeIndex` at `path` for `fingerprint`; every fault is a miss.
#[pyfunction]
fn read_scope_index_cache(
    py: Python<'_>,
    path: PathBuf,
    fingerprint: String,
) -> PyResult<Option<Py<PyAny>>> {
    let cached = py
        .compiler_detach(|| Ok(read_scope_cache(&path, &fingerprint)))
        .map_err(compiler_error)?;
    let Ok(index) = cached else {
        return Ok(None);
    };
    match index_object(&ScopeClasses::new(py)?, &index) {
        Ok(object) => Ok(Some(object.unbind())),
        Err(error) if error.is_instance_of::<PyValueError>(py) => Ok(None),
        Err(error) => Err(error),
    }
}

/// Atomically write one complete `ScopeIndex` for `fingerprint`; whether the write landed.
#[pyfunction]
fn write_scope_index_cache(
    py: Python<'_>,
    location: (PathBuf, String),
    fingerprint: String,
    index: &Bound<'_, PyAny>,
) -> PyResult<bool> {
    if !read_completeness(index)?.iter().all(|done| *done) {
        return Ok(false);
    }
    let index: CachedIndex = read_index(index)?;
    let (directory, file_name) = location;
    py.compiler_detach(|| {
        Ok(match encode_scope_cache(&index, &fingerprint) {
            Ok(envelope) => matches!(write_scope_cache(&directory, &file_name, &envelope), Ok(())),
            Err(_) => false,
        })
    })
    .map_err(compiler_error)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(scope_index_fingerprint, module)?)?;
    module.add_function(wrap_pyfunction!(read_scope_index_cache, module)?)?;
    module.add_function(wrap_pyfunction!(write_scope_index_cache, module)?)?;
    Ok(())
}
