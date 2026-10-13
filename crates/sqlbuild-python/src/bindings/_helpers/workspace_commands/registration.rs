//! Register the playground and skills commands.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::workspace_commands::commands;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    commands::register(module)
}
