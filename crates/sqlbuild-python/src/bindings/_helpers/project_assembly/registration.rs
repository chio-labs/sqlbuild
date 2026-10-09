//! Register the native project assembly functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::project_assembly::resources;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    resources::register(module)
}
