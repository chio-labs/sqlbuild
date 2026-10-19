use crate::models::ConfigValue;

/// A configuration table holding `entries` in order.
pub(crate) fn table(entries: &[(&str, ConfigValue)]) -> ConfigValue {
    ConfigValue::Map(
        entries
            .iter()
            .map(|(key, value)| (ConfigValue::String((*key).to_owned()), value.clone()))
            .collect(),
    )
}

/// A configuration string.
pub(crate) fn text(value: &str) -> ConfigValue {
    ConfigValue::String(value.to_owned())
}
