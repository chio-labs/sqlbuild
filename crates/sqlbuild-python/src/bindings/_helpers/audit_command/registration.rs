//! Register the native `sqb audit` command.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::audit_command::command;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    command::register(module)
}
