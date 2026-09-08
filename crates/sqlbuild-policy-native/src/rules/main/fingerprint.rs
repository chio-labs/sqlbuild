use crate::models::{PolicyConfig, RuleMetadata};

pub(crate) fn fingerprint(
    rules: &[&RuleMetadata],
    config: &PolicyConfig,
    dialect: &str,
) -> Result<String, String> {
    crate::rules::_helpers::catalogue::fingerprint(rules, config, dialect)
}
