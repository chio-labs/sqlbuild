//! Register the native build, audit and test progress reporters and the build footer.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::build_progress::{audit_progress, footer, nested_progress};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    audit_progress::register(module)?;
    footer::register(module)?;
    nested_progress::register(module)
}
