//! Register the native semantic completion functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::semantic_checks::{
    completion, help_catalogue, metadata, resource_sql, type_recovery,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    type_recovery::register(module)?;
    metadata::register(module)?;
    resource_sql::register(module)?;
    help_catalogue::register(module)?;
    completion::register(module)
}
