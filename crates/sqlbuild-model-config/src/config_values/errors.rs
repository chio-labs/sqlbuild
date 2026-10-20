//! The error a typed config read returns.

use crate::config_values::models::ConfigNode;

/// A config value of the wrong type: its key, the kind expected, and the value found.
#[derive(Clone, Debug, PartialEq)]
pub struct ConfigTypeError<'a, H> {
    pub key: String,
    pub expected: &'static str,
    pub value: &'a ConfigNode<H>,
}
