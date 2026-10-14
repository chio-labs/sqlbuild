use std::collections::BTreeMap;

use crate::rule_catalogue::models::{CatalogueRule, OptionValue, RuleText};

pub(crate) struct CatalogueTestCase {
    pub(crate) description: &'static str,
    pub(crate) rules: Vec<CatalogueRule>,
    pub(crate) configured: BTreeMap<String, BTreeMap<String, OptionValue>>,
    pub(crate) expected_result: Result<Vec<usize>, &'static str>,
}

pub(crate) struct RuleTextTestCase {
    pub(crate) description: &'static str,
    pub(crate) rule: RuleText,
    pub(crate) with_config: bool,
    pub(crate) expected_text: &'static str,
}

pub(crate) struct SkillsBodyTestCase {
    pub(crate) description: &'static str,
    pub(crate) rules: Vec<RuleText>,
    pub(crate) expected_lines: Vec<&'static str>,
}

pub(crate) struct InstallTestCase {
    pub(crate) description: &'static str,
    pub(crate) existing: Option<&'static str>,
    pub(crate) state: &'static str,
    pub(crate) blocked_second: bool,
    pub(crate) expected_error: Option<&'static str>,
    pub(crate) expected_contents: [Option<&'static str>; 2],
}
