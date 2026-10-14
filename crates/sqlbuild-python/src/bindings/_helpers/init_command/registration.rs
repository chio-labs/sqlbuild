//! Register the native `sqb init` command.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::init_command::command;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    command::register(module)
}
