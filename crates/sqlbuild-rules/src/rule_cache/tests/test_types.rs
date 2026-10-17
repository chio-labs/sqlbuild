pub(crate) struct ModelRuleKeysTestCase {
    pub(crate) description: &'static str,
    pub(crate) models: Vec<(&'static str, &'static str, Option<&'static str>)>,
    pub(crate) expected_key_count: usize,
}
