//! Register the native `sqb clone` command.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::clone::clone_command;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    clone_command::register(module)
}
