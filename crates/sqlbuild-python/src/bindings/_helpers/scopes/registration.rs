//! Register the native declaration scope functions and classes.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::scopes::{
    compile_usages, declaration_contexts, placement, relationship_names, scope_cache, scope_index,
    scope_lookup, scope_reports,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    scope_index::register(module)?;
    relationship_names::register(module)?;
    declaration_contexts::register(module)?;
    placement::register(module)?;
    compile_usages::register(module)?;
    scope_lookup::register(module)?;
    scope_cache::register(module)?;
    scope_reports::register(module)?;
    Ok(())
}
