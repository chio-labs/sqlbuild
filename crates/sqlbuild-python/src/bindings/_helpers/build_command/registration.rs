//! Register the native `sqb build` command and its plan safety gates.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::build_command::{command, defer_clone, policies};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    defer_clone::register(module)?;
    policies::register(module)?;
    command::register(module)
}
