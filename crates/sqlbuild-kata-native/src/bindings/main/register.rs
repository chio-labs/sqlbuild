use pyo3::prelude::{Bound, PyModule, PyResult};
use pyo3::pymodule;

#[pymodule]
pub fn _kata_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    crate::bindings::_helpers::functions::register(module)
}
