pub(crate) struct HostedKeyTestCase {
    pub(crate) description: &'static str,
    pub(crate) keys: Vec<&'static str>,
    pub(crate) expected_duplicates: Vec<&'static str>,
}

pub(crate) struct CapturedNameTestCase {
    pub(crate) description: &'static str,
    pub(crate) native: &'static str,
    pub(crate) expected_python: Option<&'static str>,
}
