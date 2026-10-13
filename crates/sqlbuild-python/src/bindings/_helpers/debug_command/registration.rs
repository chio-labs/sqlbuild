//! Register the `sqb debug` command.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::debug_command::run_debug;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    run_debug::register(module)
}
