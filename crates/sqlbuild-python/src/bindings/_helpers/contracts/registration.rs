//! Register the native contract functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::contracts::model_contracts;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    model_contracts::register(module)
}
