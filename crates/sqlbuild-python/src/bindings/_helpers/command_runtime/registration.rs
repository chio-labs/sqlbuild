//! Register command connection and warehouse resolution.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::command_runtime::{
    adapters, connection, preview_target, warehouse_scope, warehouses,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    adapters::register(module)?;
    warehouse_scope::register(module)?;
    warehouses::register(module)?;
    connection::register(module)?;
    preview_target::register(module)
}
