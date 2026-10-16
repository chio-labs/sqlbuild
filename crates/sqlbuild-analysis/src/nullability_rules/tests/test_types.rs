pub(crate) struct NullabilityRuleTestCase {
    pub(crate) description: &'static str,
    pub(crate) arguments: Vec<&'static str>,
    pub(crate) expected_first_arg: &'static str,
    pub(crate) expected_conditional: &'static str,
    pub(crate) expected_safe_cast: &'static str,
}
