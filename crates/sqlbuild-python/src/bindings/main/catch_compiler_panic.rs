pub(crate) fn catch_compiler_panic<T>(
    operation: impl FnOnce() -> Result<T, String>,
) -> Result<T, String> {
    crate::bindings::_helpers::panics::catch_compiler_panic(operation)
}
