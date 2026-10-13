//! Register the native declaration scope functions and classes.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::scopes::{
    compile_usages, declaration_contexts, relationship_names, scope_cache, scope_command,
    scope_index, scope_loading, scope_lookup, scope_reports, scope_validation, scope_visibility,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    scope_index::register(module)?;
    relationship_names::register(module)?;
    declaration_contexts::register(module)?;
    compile_usages::register(module)?;
    scope_lookup::register(module)?;
    scope_cache::register(module)?;
    scope_loading::register(module)?;
    scope_reports::register(module)?;
    scope_command::register(module)?;
    scope_validation::register(module)?;
    scope_visibility::register(module)?;
    Ok(())
}
