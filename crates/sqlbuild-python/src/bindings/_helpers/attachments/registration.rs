//! Register the native compile attachment functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::attachments::{
    audit_rendering, ceremonial_select, cursor_intrinsics, seed_pairing, test_parameters,
    test_targets,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    audit_rendering::register(module)?;
    seed_pairing::register(module)?;
    cursor_intrinsics::register(module)?;
    test_parameters::register(module)?;
    ceremonial_select::register(module)?;
    test_targets::register(module)?;
    Ok(())
}
