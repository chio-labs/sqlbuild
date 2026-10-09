//! Register the native SQL test planning and assembly functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::sql_test_glue::{assembly, planning};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    planning::register(module)?;
    assembly::register(module)
}
