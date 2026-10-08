//! Register the shared native store functions and classes.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::cache::{native_store, sql_test_scan_store};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    native_store::register(module)?;
    sql_test_scan_store::register(module)?;
    Ok(())
}
