pub(super) struct PanicTestCase {
    pub(super) description: &'static str,
    pub(super) operation: fn() -> Result<(), String>,
    pub(super) expected_named_error: bool,
}
