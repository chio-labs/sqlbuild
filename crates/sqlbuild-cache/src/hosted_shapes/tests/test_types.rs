pub(crate) struct HostedKeyTestCase {
    pub(crate) description: &'static str,
    pub(crate) keys: Vec<&'static str>,
    pub(crate) expected_duplicates: Vec<&'static str>,
}

pub(crate) struct NativeNameTestCase {
    pub(crate) description: &'static str,
    pub(crate) shape: (&'static str, &'static str),
    pub(crate) expected_native: Option<&'static str>,
}
