//! Register the native compile output functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::compile_outputs::{artifacts, json_report, reuse};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    artifacts::register(module)?;
    json_report::register(module)?;
    reuse::register(module)
}
