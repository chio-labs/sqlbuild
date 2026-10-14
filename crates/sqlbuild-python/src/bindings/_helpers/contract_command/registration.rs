//! Register the native `sqb contract` command.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::contract_command::command;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    command::register(module)
}
