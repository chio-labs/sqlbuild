//! Recursive macro call presence over authored config values.

use crate::config_presence::_helpers::macro_calls::macro_call;
use crate::config_presence::_helpers::scan::scan;
use crate::config_presence::models::Presence;
use crate::types::AuthoredNode;

/// Return whether `MACRO_CALL_PATTERN` matches any nested string, or defer to Python.
pub fn contains_macro_call<N: AuthoredNode>(node: &N) -> Presence {
    scan(node, &macro_call)
}
