//! Register the native SQL test planning functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::sql_test_glue::planning;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    planning::register(module)
}
