use pyo3::prelude::{Bound, PyModule, PyResult};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    crate::bindings::_helpers::auditing::identity::register(module)?;
    crate::bindings::_helpers::auditing::measurement::register(module)?;
    crate::bindings::_helpers::auditing::render::register(module)?;
    crate::bindings::_helpers::auditing::schema_audits::register(module)
}
