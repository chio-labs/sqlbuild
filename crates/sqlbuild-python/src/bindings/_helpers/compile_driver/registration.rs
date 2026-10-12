//! Register the native compile command driver.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::compile_driver::{analysis, command, discovery, inputs, project};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    analysis::register(module)?;
    command::register(module)?;
    project::register(module)?;
    inputs::register(module)?;
    discovery::register(module)
}
