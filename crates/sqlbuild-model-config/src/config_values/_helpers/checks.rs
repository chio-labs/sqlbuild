//! The authored value of a config key and the type error a reader raises for it.

use crate::config_values::errors::ConfigTypeError;
use crate::config_values::models::ConfigNode;

/// `values.get(key)` unless it is `None`.
pub(crate) fn authored<H>(value: Option<&ConfigNode<H>>) -> Option<&ConfigNode<H>> {
    value.filter(|value| !matches!(value, ConfigNode::Null))
}

/// The error naming `key`, the `expected` kind and the value found.
pub(crate) fn wrong_type<'a, H>(
    key: &str,
    expected: &'static str,
    value: &'a ConfigNode<H>,
) -> ConfigTypeError<'a, H> {
    ConfigTypeError {
        key: key.to_owned(),
        expected,
        value,
    }
}
