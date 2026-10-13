//! Register the native fingerprint storage functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::fingerprints::{latest_rows, storage_sql};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    storage_sql::register(module)?;
    latest_rows::register(module)
}
