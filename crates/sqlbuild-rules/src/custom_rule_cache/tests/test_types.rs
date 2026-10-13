pub(crate) struct IdentityTestCase {
    pub(crate) description: &'static str,
    pub(crate) edit: fn(&mut crate::custom_rule_cache::models::RuleIdentityInput),
    pub(crate) expected_changed: bool,
}

pub(crate) struct LookupTestCase {
    pub(crate) description: &'static str,
    pub(crate) current_digest: &'static str,
    pub(crate) model_name: &'static str,
    pub(crate) expected_plan: Vec<(&'static str, Option<Vec<&'static str>>)>,
    pub(crate) expected_hits: usize,
}
