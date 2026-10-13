//! Register the compiler frontier and its stage captures.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::frontier::{compile_frontier, stage_capture};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    compile_frontier::register(module)?;
    stage_capture::register(module)
}
