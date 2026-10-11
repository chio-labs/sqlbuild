//! Canonical snake_case resource identity checks.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyString, PyStringMethods};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_model_config::resource_identities::main::resource_identity_failure::resource_identity_failure;

/// The snake_case suggestion and help for a non-canonical identity, or `None`.
#[pyfunction]
fn resource_identity_suggestion(
    name: &Bound<'_, PyString>,
    private_identity: bool,
) -> PyResult<Option<(String, String)>> {
    let text = name.to_string_lossy();
    Ok(resource_identity_failure(&text, private_identity))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(resource_identity_suggestion, module)?)
}
