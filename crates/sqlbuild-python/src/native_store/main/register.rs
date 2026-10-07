//! Register the shared native store's functions on the extension module.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::wrap_pyfunction;

use crate::native_store::_helpers::functions::{content_digest, fingerprint_project_files};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(content_digest, module)?)?;
    module.add_function(wrap_pyfunction!(fingerprint_project_files, module)?)?;
    Ok(())
}
