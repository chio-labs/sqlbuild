//! Register the native SQL test planning and assembly functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::sql_test_glue::{authored_ctes, compiled_tests, planning};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    authored_ctes::register(module)?;
    planning::register(module)?;
    compiled_tests::register(module)
}
