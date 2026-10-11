//! Register the native compile attachment functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::attachments::{
    ceremonial_select, cursor_intrinsics, reference_markers,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    cursor_intrinsics::register(module)?;
    ceremonial_select::register(module)?;
    reference_markers::register(module)?;
    Ok(())
}
