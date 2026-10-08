//! Register the native type system functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::type_system::normalization;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    normalization::register(module)?;
    Ok(())
}
