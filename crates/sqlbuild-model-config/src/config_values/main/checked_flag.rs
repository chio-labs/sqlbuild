//! A config boolean read with its type checked.

use crate::config_values::_helpers::checks::{authored, wrong_type};
use crate::config_values::constants::EXPECTED_FLAG;
use crate::config_values::errors::ConfigTypeError;
use crate::config_values::models::ConfigNode;
use crate::config_values::types::HostObject;
use crate::types::{AuthoredNode, NodeKind};

/// The boolean value of `key`, or `None` when absent or `None`.
pub fn checked_flag<'a, H: HostObject>(
    key: &str,
    value: Option<&'a ConfigNode<H>>,
) -> Result<Option<bool>, ConfigTypeError<'a, H>> {
    let Some(value) = authored(value) else {
        return Ok(None);
    };
    match value.kind() {
        NodeKind::Bool(flag) => Ok(Some(flag)),
        _ => Err(wrong_type(key, EXPECTED_FLAG, value)),
    }
}
