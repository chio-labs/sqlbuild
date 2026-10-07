//! Register the native project discovery functions and classes.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::discovery::{declaration_files, project_files};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    project_files::register(module)?;
    declaration_files::register(module)?;
    Ok(())
}
