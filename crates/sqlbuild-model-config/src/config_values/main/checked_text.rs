//! A config string read with its type checked.

use crate::config_values::_helpers::checks::{authored, wrong_type};
use crate::config_values::constants::EXPECTED_TEXT;
use crate::config_values::errors::ConfigTypeError;
use crate::config_values::models::ConfigNode;
use crate::config_values::types::HostObject;
use crate::types::{AuthoredNode, NodeKind};

/// The value of `key` when it is a string (a present empty string included), or `None` when absent or `None`.
pub fn checked_text<'a, H: HostObject>(
    key: &str,
    value: Option<&'a ConfigNode<H>>,
) -> Result<Option<&'a ConfigNode<H>>, ConfigTypeError<'a, H>> {
    let Some(value) = authored(value) else {
        return Ok(None);
    };
    match value.kind() {
        NodeKind::Str => Ok(Some(value)),
        _ => Err(wrong_type(key, EXPECTED_TEXT, value)),
    }
}
