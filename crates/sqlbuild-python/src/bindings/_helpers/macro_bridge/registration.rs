//! Register the macro bridge's persistent store keys and module digests.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::macro_bridge::{first_compile, module_digests, store_keys};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    first_compile::register(module)?;
    module_digests::register(module)?;
    store_keys::register(module)
}
