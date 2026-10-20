//! A config cursor bound read with its type checked.

use crate::config_values::_helpers::checks::{authored, wrong_type};
use crate::config_values::constants::EXPECTED_CURSOR_BOUND;
use crate::config_values::errors::ConfigTypeError;
use crate::config_values::models::{ConfigNode, CursorBound};
use crate::config_values::types::HostObject;
use crate::types::{AuthoredNode, NodeKind};

/// How `key` reads as a cursor bound: a string, a non-boolean integer, a date or a datetime.
pub fn checked_cursor_bound<'a, H: HostObject>(
    key: &str,
    value: Option<&'a ConfigNode<H>>,
) -> Result<Option<CursorBound<'a, H>>, ConfigTypeError<'a, H>> {
    let Some(value) = authored(value) else {
        return Ok(None);
    };
    if value.is_date_like() {
        return Ok(Some(CursorBound::Dated(value)));
    }
    match value.kind() {
        NodeKind::Str | NodeKind::Int { .. } => Ok(Some(CursorBound::Stringified(value))),
        _ => Err(wrong_type(key, EXPECTED_CURSOR_BOUND, value)),
    }
}
