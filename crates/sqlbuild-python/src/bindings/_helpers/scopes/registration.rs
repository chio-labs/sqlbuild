//! Register the native declaration scope functions and classes.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::scopes::{declaration_contexts, relationship_names, scope_index};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    scope_index::register(module)?;
    relationship_names::register(module)?;
    declaration_contexts::register(module)?;
    Ok(())
}
