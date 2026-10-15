//! Register the generated relation name fitting functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::relation_naming::fitting;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    fitting::register(module)
}
