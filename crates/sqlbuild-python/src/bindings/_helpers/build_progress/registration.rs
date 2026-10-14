//! Register the native build progress reporter and footer.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::build_progress::footer;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    footer::register(module)
}
