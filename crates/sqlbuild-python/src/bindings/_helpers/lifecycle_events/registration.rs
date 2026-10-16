//! Register lifecycle event catalogue queries, constants and envelope validation.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::lifecycle_events::{catalog, envelopes, validation};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    catalog::register(module)?;
    envelopes::register(module)?;
    validation::register(module)
}
