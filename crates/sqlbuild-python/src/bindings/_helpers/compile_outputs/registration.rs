//! Register the native compile output functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::compile_outputs::{json_report, reuse, runtime_target};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    json_report::register(module)?;
    reuse::register(module)?;
    runtime_target::register(module)
}
