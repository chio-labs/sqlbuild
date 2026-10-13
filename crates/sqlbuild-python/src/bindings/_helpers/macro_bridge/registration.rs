//! Register the macro bridge's persistent store keys.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::macro_bridge::store_keys;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    store_keys::register(module)
}
