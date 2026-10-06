use crate::models::ConfigValue;

/// A table from string keys, in the given order.
pub(super) fn table(entries: Vec<(&str, ConfigValue)>) -> ConfigValue {
    ConfigValue::Map(
        entries
            .into_iter()
            .map(|(key, value)| (ConfigValue::String(key.to_owned()), value))
            .collect(),
    )
}
