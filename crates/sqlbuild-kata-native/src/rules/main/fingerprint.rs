use crate::models::{KataConfig, RuleMetadata};

pub(crate) fn fingerprint(rules: &[&RuleMetadata], config: &KataConfig) -> Result<String, String> {
    crate::rules::_helpers::catalogue::fingerprint(rules, config)
}
