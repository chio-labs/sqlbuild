use crate::models::RuleMetadata;

pub fn catalogue() -> Vec<RuleMetadata> {
    crate::rules::_helpers::catalogue::catalogue()
}
