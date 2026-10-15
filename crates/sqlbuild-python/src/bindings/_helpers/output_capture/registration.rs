//! Register native command-output capture.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::output_capture::{context, dispatcher, records, text};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    context::register(module)?;
    dispatcher::register(module)?;
    records::register(module)?;
    text::register(module)
}
