//! Register command connection and warehouse resolution.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::command_runtime::{connection, preview_target, warehouses};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    warehouses::register(module)?;
    connection::register(module)?;
    preview_target::register(module)
}
