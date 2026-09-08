use crate::models::PolicyConfig;

pub(crate) fn validate(config: &PolicyConfig) -> Result<(), String> {
    crate::configuration::_helpers::loading::validate(config)
}
