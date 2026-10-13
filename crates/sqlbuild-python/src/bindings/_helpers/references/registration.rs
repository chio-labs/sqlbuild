use pyo3::prelude::{Bound, PyModule, PyResult};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    crate::bindings::_helpers::references::relations::register(module)?;
    crate::bindings::_helpers::references::source_relations::register(module)
}
