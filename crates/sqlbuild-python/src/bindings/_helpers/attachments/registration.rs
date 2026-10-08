//! Register the native compile attachment functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::attachments::{audit_rendering, cursor_intrinsics, seed_pairing};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    audit_rendering::register(module)?;
    seed_pairing::register(module)?;
    cursor_intrinsics::register(module)?;
    Ok(())
}
