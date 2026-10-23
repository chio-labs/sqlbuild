//! Register the base-revision compile entry that `--since` runs in a separate interpreter.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::change_selection::base_compile;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    base_compile::register(module)
}
