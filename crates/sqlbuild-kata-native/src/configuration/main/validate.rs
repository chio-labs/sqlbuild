use crate::models::KataConfig;

pub(crate) fn validate(config: &KataConfig) -> Result<(), String> {
    crate::configuration::_helpers::loading::validate(config)
}
