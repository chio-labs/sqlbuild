//! Register the compiler frontier and its stage captures.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::frontier::{cache_directory, compile_frontier, stage_capture};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    cache_directory::register(module)?;
    compile_frontier::register(module)?;
    stage_capture::register(module)
}
