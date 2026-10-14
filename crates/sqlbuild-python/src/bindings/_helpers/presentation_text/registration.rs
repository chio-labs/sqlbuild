//! Register the shared CLI text helpers.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::presentation_text::{document, functions, terminal};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    document::register(module)?;
    functions::register(module)?;
    terminal::register(module)
}
