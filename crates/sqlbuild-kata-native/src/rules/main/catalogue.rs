use crate::models::RuleMetadata;

pub(crate) fn catalogue() -> Vec<RuleMetadata> {
    crate::rules::_helpers::catalogue::catalogue()
}
