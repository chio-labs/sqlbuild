//! Mapping key identity for constructed YAML mappings.

use crate::models::ConfigValue;

/// Whether the value can be a mapping key: collections cannot.
pub(crate) fn is_hashable(value: &ConfigValue) -> bool {
    !matches!(value, ConfigValue::List(_) | ConfigValue::Map(_))
}

/// Text equal for two scalar keys exactly when they are the same value.
pub(crate) fn key_identity(value: &ConfigValue) -> String {
    match value {
        ConfigValue::Float(number) if number.is_nan() => "float:nan".to_owned(),
        ConfigValue::Float(number) => format!("float:{}", number.to_bits()),
        other => format!("{other:?}"),
    }
}
