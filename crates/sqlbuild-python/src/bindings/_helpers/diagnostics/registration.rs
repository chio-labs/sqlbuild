//! Register diagnostics console formatting, redaction and process trackers.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::diagnostics::{console_records, log_records, redaction, trackers};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    console_records::register(module)?;
    log_records::register(module)?;
    redaction::register(module)?;
    trackers::register(module)
}
