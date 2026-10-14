//! Register pure migration helpers.

use pyo3::prelude::{Bound, PyModule, PyResult};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    super::columns::register(module)?;
    super::projections::register(module)?;
    super::fingerprint::register(module)
}
