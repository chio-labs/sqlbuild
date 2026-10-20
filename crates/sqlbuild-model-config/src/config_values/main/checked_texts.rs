//! A config sequence of strings read with its type checked.

use crate::config_values::_helpers::checks::{authored, wrong_type};
use crate::config_values::constants::EXPECTED_TEXTS;
use crate::config_values::errors::ConfigTypeError;
use crate::config_values::models::ConfigNode;
use crate::config_values::types::HostObject;
use crate::types::{AuthoredNode, NodeKind};

/// The string items of `key` when it is a list or tuple of strings, or `None` when absent or `None`.
pub fn checked_texts<'a, H: HostObject>(
    key: &str,
    value: Option<&'a ConfigNode<H>>,
) -> Result<Option<Vec<&'a ConfigNode<H>>>, ConfigTypeError<'a, H>> {
    let Some(value) = authored(value) else {
        return Ok(None);
    };
    let items: Vec<&ConfigNode<H>> = match value.kind() {
        NodeKind::List | NodeKind::Tuple => (&value).items(),
        _ => return Err(wrong_type(key, EXPECTED_TEXTS, value)),
    };
    if items.iter().all(|item| item.kind() == NodeKind::Str) {
        Ok(Some(items))
    } else {
        Err(wrong_type(key, EXPECTED_TEXTS, value))
    }
}
