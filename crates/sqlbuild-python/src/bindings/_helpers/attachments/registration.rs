//! Register the native compile attachment functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::attachments::audit_rendering;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    audit_rendering::register(module)?;
    Ok(())
}
