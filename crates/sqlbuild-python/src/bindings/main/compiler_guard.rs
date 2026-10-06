pub(crate) fn compiler_guard<T>(
    operation: impl FnOnce() -> pyo3::PyResult<T>,
) -> pyo3::PyResult<T> {
    crate::bindings::_helpers::panics::compiler_guard(operation)
}
