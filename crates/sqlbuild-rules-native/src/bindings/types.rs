pub(crate) trait CompilerDetach {
    fn compiler_detach<T: Send, F: FnOnce() -> Result<T, String> + Send>(
        self,
        operation: F,
    ) -> Result<T, String>;
}
