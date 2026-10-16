use pyo3::prelude::{Bound, PyModule, PyResult};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    crate::bindings::_helpers::authored_values::fields::register(module)?;
    crate::bindings::_helpers::authored_values::project_vars::register(module)?;
    crate::bindings::_helpers::authored_values::python_nodes::register(module)
}
