//! Register the native `sqb` argument parsing and command dispatch.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::cli::{argv, entry};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    argv::register(module)?;
    entry::register(module)?;
    Ok(())
}
