pub(crate) const API_VERSION: u32 = 1;
pub(crate) const SCOPE_METADATA_SCHEMA_VERSION: u32 = 2;
pub(crate) const BUILT_IN_RULE_NAMESPACE: &str = "SQBR";
pub(crate) const PIPELINE_SUBJECT: &str = "pipeline";
pub(crate) const GENERIC_TEST_NAME: &str = "test";
pub(crate) const GENERIC_WORKS_NAME: &str = "works";
pub(crate) const GENERIC_BASIC_NAME: &str = "basic";
pub(crate) const GENERIC_SCENARIO_NAME: &str = "scenario";
pub(crate) const GENERIC_CASE_NAME: &str = "case";
pub(crate) const CUSTOM_RULE_NAMESPACE: &str = "XSQBR";
pub(crate) const TARGET_DIRECTORY: &str = "target";
pub(crate) const REFERENCE_KIND: &str = "ref";
pub(crate) const VIEW_MATERIALIZATION: &str = "view";
pub(crate) const ENFORCED_CONTRACT: &str = "enforced";
pub(crate) const BOOLEAN_TYPE: &str = "BOOLEAN";
pub(crate) const TIMESTAMP_TYPE: &str = "TIMESTAMP";
pub(crate) const DATE_TYPE: &str = "DATE";
pub(crate) const NEGATION_OPERATOR: &str = "-";
pub(crate) const DECLARATION_DOMAIN_COMPONENTS: usize = 3;

#[derive(Clone, Copy, Debug, Default)]
pub(crate) struct RulesCodeGrammar;

impl fensu_policy::policy::types::RuleCodeGrammar for RulesCodeGrammar {
    fn rule_code_is_exact(&self, value: &str) -> bool {
        let Some((namespace, remainder)) = namespace_and_remainder(value) else {
            return false;
        };
        if remainder.len() < 3 {
            return false;
        }
        let (family, number) = remainder.split_at(remainder.len() - 3);
        let family_valid = family.bytes().all(|value| value.is_ascii_uppercase());
        let number_valid = number.bytes().all(|value| value.is_ascii_digit());
        number_valid && family_valid && (namespace == CUSTOM_RULE_NAMESPACE || !family.is_empty())
    }

    fn rule_selector_is_valid(&self, value: &str) -> bool {
        let Some((_, remainder)) = namespace_and_remainder(value) else {
            return false;
        };
        remainder.is_empty()
            || remainder.bytes().all(|value| value.is_ascii_uppercase())
            || self.rule_code_is_exact(value)
    }
}

fn namespace_and_remainder(value: &str) -> Option<(&'static str, &str)> {
    if let Some(remainder) = value.strip_prefix(CUSTOM_RULE_NAMESPACE) {
        return Some((CUSTOM_RULE_NAMESPACE, remainder));
    }
    value
        .strip_prefix(BUILT_IN_RULE_NAMESPACE)
        .map(|remainder| (BUILT_IN_RULE_NAMESPACE, remainder))
}
