pub(super) struct UnknownKeysTestCase {
    pub(super) description: &'static str,
    pub(super) keys: Vec<(String, bool)>,
    pub(super) expected_failure: Option<(&'static str, &'static str)>,
}
