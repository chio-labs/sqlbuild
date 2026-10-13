//! Register the native cursor algebra functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::cursor::{durations, intervals, scalars};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    scalars::register(module)?;
    intervals::register(module)?;
    durations::register(module)?;
    Ok(())
}
