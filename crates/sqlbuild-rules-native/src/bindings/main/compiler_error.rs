pub(crate) fn compiler_error(error: impl std::fmt::Display) -> pyo3::PyErr {
    crate::bindings::_helpers::panics::compiler_error(error)
}
