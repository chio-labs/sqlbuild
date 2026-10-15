use pyo3::prelude::{Bound, PyModule, PyResult};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    crate::bindings::_helpers::graph::project_graph::register(module)?;
    crate::bindings::_helpers::graph::algorithms::register(module)?;
    crate::bindings::_helpers::graph::execution_gates::register(module)?;
    crate::bindings::_helpers::graph::python_selection::register(module)?;
    crate::bindings::_helpers::graph::python_lifecycle::register(module)?;
    crate::bindings::_helpers::graph::python_node_graph::register(module)?;
    crate::bindings::_helpers::graph::views::register(module)
}
