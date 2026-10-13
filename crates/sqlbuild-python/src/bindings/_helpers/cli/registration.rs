//! Register the native `sqb` argument parsing and command dispatch.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::cli::{argv, dispatch};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    argv::register(module)?;
    dispatch::register(module)?;
    Ok(())
}
