//! Register the native SQL test planning functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

pub(crate) fn register(_module: &Bound<'_, PyModule>) -> PyResult<()> {
    Ok(())
}
