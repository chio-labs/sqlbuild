//! Register the native warehouse state row functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::state_rows::{events, freshness};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    events::register(module)?;
    freshness::register(module)?;
    Ok(())
}
