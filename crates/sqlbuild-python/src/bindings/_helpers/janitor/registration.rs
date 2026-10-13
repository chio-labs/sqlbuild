//! Register the native `sqb janitor` command and its plan rendering.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::janitor::{janitor_command, janitor_plan};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    janitor_command::register(module)?;
    janitor_plan::register(module)
}
