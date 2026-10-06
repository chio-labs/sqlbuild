use crate::models::{CustomRule, RuleMetadata};

pub(crate) fn assemble_catalogue(custom: &[CustomRule]) -> Result<Vec<RuleMetadata>, String> {
    crate::rules::_helpers::catalogue::with_custom(custom)
}
