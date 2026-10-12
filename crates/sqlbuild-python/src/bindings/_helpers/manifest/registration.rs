//! Register the manifest builder.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::manifest::builder;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    builder::register(module)
}
