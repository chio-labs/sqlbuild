pub(crate) struct SinceReferenceTestCase {
    pub(crate) description: &'static str,
    pub(crate) value: &'static str,
    pub(crate) configured: Option<&'static str>,
    /// The resolved ref, or the error code.
    pub(crate) expected: Result<&'static str, &'static str>,
}

pub(crate) struct GitBaseFailureTestCase {
    pub(crate) description: &'static str,
    pub(crate) reference: &'static str,
    pub(crate) expected_code: &'static str,
    pub(crate) expected_message_fragment: &'static str,
}
