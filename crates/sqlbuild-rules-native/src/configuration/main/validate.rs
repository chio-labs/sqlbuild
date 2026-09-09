use crate::models::RulesConfig;

pub(crate) fn validate(config: &RulesConfig) -> Result<(), String> {
    crate::configuration::_helpers::loading::validate(config)
}
